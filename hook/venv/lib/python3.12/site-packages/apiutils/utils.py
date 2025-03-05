# encoding: utf-8
from __future__ import absolute_import, unicode_literals

import datetime
import os
import posixpath
import tempfile
import hashlib
import json

from django import forms
from django.conf import settings
from django.db import models, transaction
from django.shortcuts import render
from django.contrib.auth import models as auth_models
from django.utils.deconstruct import deconstructible
from django.utils.encoding import force_bytes
from django.db.models.fields import reverse_related
from import_export.formats import base_formats
from rest_framework.decorators import api_view, renderer_classes
from rest_framework.renderers import StaticHTMLRenderer
from rest_framework.response import Response

from apiview import model, admin, view, utility, serializer, common_view, admintools, descriptors, filters
from apiview.views import fields
from apiview.err_code import ErrCode
from apiview.exceptions import CustomError

from . import constants, renderers


class ManyToManyRel(reverse_related.ForeignObjectRel):
    def __init__(self, field, to, related_name=None, related_query_name=None,
                 limit_choices_to=None, symmetrical=True, through=None,
                 through_fields=None, db_constraint=False):
        super(ManyToManyRel, self).__init__(
            field, to,
            related_name=related_name,
            related_query_name=related_query_name,
            limit_choices_to=limit_choices_to,
        )

        self.through = through

        if through_fields and not through:
            raise ValueError("Cannot specify through_fields without a through model")
        self.through_fields = through_fields

        self.symmetrical = symmetrical
        self.db_constraint = db_constraint

    def get_related_field(self):
        opts = self.through._meta
        field = None
        if self.through_fields:
            field = opts.get_field(self.through_fields[0])
        else:
            for field in opts.fields:
                rel = getattr(field, 'remote_field', None)
                if rel and rel.model == self.model:
                    break
        if field is None:
            return None
        else:
            return field.foreign_related_fields[0]


class ManyToManyField(models.ManyToManyField):

    rel_class = ManyToManyRel

    def __init__(self, to, related_name=None, related_query_name=None, limit_choices_to=None, symmetrical=None,
                 through=None, through_fields=None, db_constraint=False, db_table=None, swappable=True, **kwargs):
        super(ManyToManyField, self).__init__(to, related_name, related_query_name, limit_choices_to, symmetrical,
                                              through, through_fields, db_constraint, db_table, swappable, **kwargs)


class ForeignKey(models.ForeignKey):

    forward_related_accessor_class = descriptors.ForwardManyToOneCacheDescriptor

    def __init__(self, to, on_delete=models.DO_NOTHING, related_name=None, related_query_name=None,
                 limit_choices_to=None, parent_link=False, to_field=None, db_constraint=False,  **kwargs):
        super(ForeignKey, self).__init__(to, on_delete, related_name, related_query_name, limit_choices_to,
                                         parent_link, to_field, db_constraint, **kwargs)


class OneToOneField(models.OneToOneField):

    forward_related_accessor_class = descriptors.ForwardOneToOneCacheDescriptor

    def __init__(self, to, on_delete=models.DO_NOTHING, to_field=None, db_constraint=False, **kwargs):
        super(OneToOneField, self).__init__(to, on_delete, to_field, db_constraint=db_constraint, **kwargs)


class DeletedManager(models.Manager):

    def get_queryset(self):
        queryset = super(DeletedManager, self).get_queryset()
        return queryset.filter(delete_status=constants.DELETE_CODE.NORMAL.code)

    def get_all_queryset(self):
        return super(DeletedManager, self).get_queryset()


class BaseModel(model.BaseModel):
    id = models.BigAutoField('主键ID', primary_key=True, editable=False)
    create_time = models.DateTimeField('创建时间', auto_now_add=True, db_index=True, editable=False)
    modify_time = models.DateTimeField('修改时间', auto_now=True, db_index=True, editable=False)
    delete_status = models.BooleanField('删除状态', choices=constants.DELETE_CODE.get_list(),
                                        default=constants.DELETE_CODE.NORMAL.code, null=False, db_index=True)
    remark = models.TextField('备注说明', null=True, blank=True, default='')

    default_manager = models.Manager()
    objects = DeletedManager()

    def __str__(self):
        if hasattr(self, 'name'):
            return self.name
        else:
            return super(BaseModel, self).__str__()

    class Meta:
        abstract = True

    @classmethod
    def ex_search_fields(cls):
        ret = set()
        for field in cls._meta.fields:
            if not field.db_index and not field.unique \
                    and field.name == 'name' and isinstance(field, models.CharField):
                ret.add(field.name)
        return ret

    @classmethod
    def search_fields(cls):
        ret = super(BaseModel, cls).search_fields()
        return ret.union(cls.ex_search_fields())

    def delete(self, using=None, keep_parents=False):
        if self.delete_status == constants.DELETE_CODE.DELETED.code:
            return
        self.delete_status = constants.DELETE_CODE.DELETED.code
        return self.save(using=using, force_update=True, update_fields=['delete_status', ])
        # return super(BaseModel, self).delete(using=using, keep_parents=keep_parents)

    def un_delete(self, using=None):
        if self.delete_status == constants.DELETE_CODE.NORMAL.code:
            return
        self.delete_status = constants.DELETE_CODE.NORMAL.code
        return self.save(using=using, force_update=True, update_fields=['delete_status', ])


class ChangeLogBase(BaseModel):
    status = models.IntegerField('状态', choices=constants.CHANGE_LOG_STATUS_CODE.get_list(),
                                 default=constants.CHANGE_LOG_STATUS_CODE.PROCESSING.code, null=False, db_index=True)
    reason = models.CharField('原因', max_length=255, null=False, blank=True, default='')
    reason_type = models.CharField('关联表类型', max_length=32, null=False, blank=True, default='')
    reason_id = models.BigIntegerField('关联表ID', null=False, blank=True, default=0)
    change_value = models.DecimalField('变化数值', max_digits=12, decimal_places=2,
                                       null=False, default=0, help_text='正加负减')

    class Meta:
        index_together = ('reason_id', 'reason_type')
        abstract = True


class TreeModel(BaseModel):
    _MODEL_CACHE_TTL = 3600 * 24 * 7
    code = models.CharField('编码', max_length=16, null=False, blank=False, default='', editable=False, unique=True)
    name = models.CharField('名称', max_length=255, null=False, blank=False, default='', editable=False)
    parent = ForeignKey(
        'self',
        blank=True,
        null=True,
        db_constraint=False,
        related_name='children',
        to_field='code',
        db_column='parent_code',
        verbose_name='父编码',
        on_delete=models.DO_NOTHING,
        editable=False
    )

    @property
    def parent_codes(self):
        if self.parent is None:
            return ()
        else:
            return self.parent.parent_codes + (self.parent_id, )

    parent_codes.__doc__ = '所有层级父编码列表'

    @classmethod
    def get_obj_by_code_from_cache(cls, code):
        return cls.get_obj_by_unique_key_from_cache(code=code)

    class Meta:
        abstract = True


def gen_file_name(filename, *args, **kwargs):
    extension = os.path.splitext(filename)[1]
    time_str = datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')
    random_str = utility.id_generator(8, '0123456789')
    return "%s%s%s" % (time_str, random_str, extension)


@deconstructible
class FileUploadTo(object):

    def __init__(self, base_path):
        self.base_path = base_path

    def __call__(self, instance, filename):
        dirname = datetime.datetime.now().strftime(self.base_path)
        return posixpath.join(dirname, gen_file_name(filename))


class ExportMixin(admintools.ExportMixin):
    formats = (base_formats.XLS, )

    def async_export_data(self, func, *args, **kwargs):
        settings.async_call(func, *args, **kwargs)


class ImportMixin(admintools.ImportMixin):
    formats = (base_formats.XLS, )
    import_template_name = 'admin/import_export/ex_import.html'


class ImportExportMixin(admintools.ImportExportMixin):
    formats = (base_formats.XLS, )
    import_template_name = 'admin/import_export/ex_import.html'

    def async_export_data(self, func, *args, **kwargs):
        settings.async_call(func, *args, **kwargs)


class BaseAdmin(admin.BaseAdmin):
    extend_normal_fields = True
    exclude_list_display = ['remark', 'modify_time']
    list_display = []
    heads = ['id']
    tails = ['create_time', 'delete_status', 'remark']
    readonly_fields = ['create_time', 'modify_time']
    change_view_readonly_fields = []
    editable_fields = forms.ALL_FIELDS
    list_filter = [('create_time', filters.DateFieldListFilter), ]
    limits = None
    advanced_filter_fields = []

    def __init__(self, *args, **kwargs):
        super(BaseAdmin, self).__init__(*args, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        db_field.remote_field.through._meta.auto_created = True
        return super(BaseAdmin, self).formfield_for_manytomany(db_field, request, **kwargs)

    def delete_queryset(self, request, queryset):
        # 单独调用每个model的delete，可以同时清空缓存
        with transaction.atomic():
            for obj in queryset:
                self.delete_model(request, obj)


class ImportAdmin(ImportMixin, BaseAdmin):
    pass


class ExportAdmin(ExportMixin, BaseAdmin):
    pass


class ImportExportAdmin(ImportExportMixin, BaseAdmin):
    pass


def site_register(model_or_iterable, admin_class=None, site=None, dismiss_create_time=False, **options):
    if admin_class is None:
        admin_class = BaseAdmin
    if not isinstance(model_or_iterable, (list, set, tuple)):
        model_or_iterable = [model_or_iterable]
    for m in model_or_iterable:
        if issubclass(m, BaseModel):
            if 'list_filter' in options and not dismiss_create_time and 'create_time' not in options['list_filter']:
                options['list_filter'] = ['create_time', ] + list(options['list_filter'])
        admin.site_register(m, admin_class, site, **options)


class APIBase(view.APIView):
    ERROR_CODE_STATUS_CODE = getattr(settings, 'ERROR_CODE_STATUS_CODE', 400)
    PARAM_ERRORS_STATUS_CODE = getattr(settings, 'PARAM_ERRORS_STATUS_CODE', 400)
    SUCCESS_WITH_CODE = getattr(settings, 'SUCCESS_WITH_CODE', True)
    return_serializer_cls = None

    @classmethod
    def get_return_info(cls, request=None, **kwargs):
        return None if cls.return_serializer_cls is None else get_serializer_info(cls.return_serializer_cls())

    @classmethod
    def get_return_simple(cls, request=None, **kwargs):
        return None

    def get_context(self, request, *args, **kwargs):
        raise NotImplementedError

    @staticmethod
    def get_req_body(request):
        return request.body if request.method == 'POST' else None

    class Meta:
        path = '/'
        param_fields = (
            ('channel', fields.CharField(help_text='App Channel', required=False)),
            ('version', fields.CharField(help_text='App Version', required=False)),
        )


class AdminApi(APIBase):

    need_superuser = True

    def get_context(self, request, *args, **kwargs):
        raise NotImplementedError

    def check_api_permissions(self, request, *args, **kwargs):
        if not isinstance(request.user, auth_models.AbstractUser):
            raise CustomError(ErrCode.ERR_AUTH_NOLOGIN)
        if not request.user.is_active or not request.user.is_staff:
            raise CustomError(ErrCode.ERR_AUTH_PERMISSION)
        if self.need_superuser:
            if not request.user.is_superuser:
                raise CustomError(ErrCode.ERR_AUTH_PERMISSION)

    class Meta:
        path = '/'


class PageMixin(object):
    PAGE_SIZE_MAX = 200
    param_fields = (
        ('page', fields.IntegerField(help_text='页码', required=False, omit=1)),
        ('page_size', fields.IntegerField(help_text='每页条数', required=False, omit=100)),
    )

    @classmethod
    def get_page_return_info(cls, data_serializer_cls):
        return {
            'page_size': '每页条数',
            'list': get_serializer_info(data_serializer_cls(), force_many=True),
            'page': '页码',
            'total_page': '总页数',
            'total_data': '数据总条数'
        }

    def get_page_context(self, request, queryset, serializer_cls):
        page_size = request.params.page_size
        if page_size <= 0 or page_size > self.PAGE_SIZE_MAX:
            raise CustomError(ErrCode.ERR_PAGE_SIZE_ERROR)
        total_data = queryset.count()
        total_page = (total_data + page_size - 1) // page_size
        page = request.params.page
        if page < 1:
            page = 1
        elif page > total_page:
            page = total_page
        start = (page - 1) * page_size
        data = []
        if total_data > 0:
            data = serializer_cls(queryset[start:start+page_size], request=request, many=True).data

        return {'page_size': page_size, 'list': data, 'page': page, 'total_page': total_page, 'total_data': total_data}


class TextApiView(APIBase):

    def __init__(self, *args, **kwargs):
        super(TextApiView, self).__init__(*args, **kwargs)
        self.renderer_classes = (renderers.PlainTextRenderer, )

    def format_res_data(self, context, status_code=None):
        if isinstance(context, dict):
            if 'code' in context and context['code'] != 0:
                context = 'error: %d %s' % (context['code'], context.get('message', ''))
            else:
                context = utility.format_res_data(context)
        return Response(context, status=status_code)

    def get_context(self, request, *args, **kwargs):
        raise NotImplementedError

    class Meta:
        path = '/'


class HtmlApiView(APIBase):

    def __init__(self, *args, **kwargs):
        super(HtmlApiView, self).__init__(*args, **kwargs)
        self.renderer_classes = (renderers.PlainHtmlRenderer, )

    def get_context(self, request, *args, **kwargs):
        raise NotImplementedError

    def format_res_data(self, context, status_code=None):
        if isinstance(context, dict):
            return render(self.request, "error.html", context)
        return Response(context, status=status_code)

    class Meta:
        path = '/'


class BaseSerializer(serializer.BaseSerializer):

    def build_property_field(self, field_name, model_class):
        field_class, field_kwargs = super(BaseSerializer, self).build_property_field(field_name, model_class)
        field_kwargs['label'] = getattr(model_class, field_name, None).__doc__
        return field_class, field_kwargs


def get_temp_file(content):
    content = force_bytes(content)
    m = hashlib.md5()
    m.update(content)
    filename = "%s.tmp" % m.hexdigest()
    filename = os.path.join(tempfile.gettempdir(), filename)
    if not os.path.exists(filename):
        with open(filename, 'wb') as f:
            f.write(content)
    return filename


def get_list_info(serializer_obj):
    child = serializer_obj.child
    if hasattr(child, 'fields'):
        return get_serializer_info(child, force_many=True)
    return [serializer_obj.label]


def get_serializer_info(serializer_obj, force_many=False):
    ret = dict()
    for field_name, field in serializer_obj.fields.items():
        if hasattr(field, 'fields'):
            ret[field_name] = get_serializer_info(field)
        elif hasattr(field, 'child'):
            ret[field_name] = get_list_info(field)
        elif hasattr(field, 'child_relation'):
            ret[field_name] = [field.child_relation.label]
        else:
            ret[field_name] = field.label
    return [ret] if force_many else ret


def get_api_info(request):
    # api.js?ext_params=referral_code,version,device_id,channel

    ext_params_str = request.GET.get("ext_params", None)
    if ext_params_str is not None:
        ext_params = set(ext_params_str.split(','))
    else:
        ext_params = set([k for k, v in APIBase.Meta.param_fields])

    server = request.build_absolute_uri("/")[:-1]
    error_codes = list()

    for tag in ErrCode.get_tags():
        code_data = getattr(ErrCode, tag)
        error_codes.append({'key': tag, 'code': code_data.code, 'message': code_data.message})

    apis = list()
    for v in common_view.get_view_list():
        if issubclass(v['viewclass'], (TextApiView, HtmlApiView, AdminApi)):
            continue
        hasfile = False
        post = False
        length = 0
        no_len_count = 0
        params = list()
        for param, field in v['params'].items():
            if isinstance(field, (fields.FileField, fields.ImageField)):
                hasfile = True
                post = True
            if param in ext_params:
                continue
            if param in ('pass', 'password'):
                post = True
            if isinstance(field, fields.CharField):
                if field.max_length is None:
                    no_len_count += 1
                else:
                    length += field.max_length
            params.append({
                'field': param,
                'name': field.help_text,
                'info': field.field_info,
                'default': '%s' % field.default,
                'omit': '%s' % field.omit,
                'required': field.required,
                'type': field.type_name
            })
        if no_len_count > 3 or length > 200:
            post = True

        api_info = {
            'name': v['name'],
            'url': v['url'],
            'ul_name': v['url'].replace('/', '_').strip('_'),
            'params': params,
            'suggest_method': 'POST' if post else 'GET',
            'content_type': 'multipart/form-data' if hasfile else 'application/x-www-form-urlencoded',
        }

        for key in ('return_info', 'return_simple'):
            value = getattr(v['viewclass'], 'get_%s' % key, None)
            if callable(value):
                value = value(request=request)
            if isinstance(value, (dict, list)):
                if v['viewclass'].SUCCESS_WITH_CODE:
                    if not isinstance(value, dict) or 'code' not in value:
                        value = v['viewclass'].get_default_context(data=value)
                value = json.dumps(value, ensure_ascii=False, indent=2)
            api_info[key] = value
        apis.append(api_info)
    return {
        'server': server,
        'ext_params': list(ext_params),
        'error_codes': error_codes,
        'apis': apis
    }


@api_view(["GET"])
@renderer_classes((StaticHTMLRenderer,))
def generate_api_info(request, template_name='apiutils/api_info.js', content_type='text/javascript;charset=utf-8'):
    info = get_api_info(request)
    if template_name is None:
        return Response(json.dumps(info, ensure_ascii=False).encode("utf8"), content_type='text/json;charset=utf-8')
    else:
        return render(request, template_name, context=info, content_type=content_type)
