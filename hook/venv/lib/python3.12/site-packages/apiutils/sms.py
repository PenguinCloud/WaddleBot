# encoding: utf-8
from __future__ import absolute_import, unicode_literals

import json

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest


client = None


def get_client():
    global client
    if client is None:
        from django.conf import settings
        client = AcsClient(settings.SMS_ACCESS_KEY_ID, settings.SMS_ACCESS_KEY_SECRET, 'cn-hangzhou')
    return client


def send_sms_batch_number(phone_numbers, sign_name, template_code, template_param, batch_size=900):
    phone_numbers = list(phone_numbers)
    ret = list()
    for pns in [phone_numbers[i:i+batch_size] for i in range(0, len(phone_numbers), batch_size)]:
        ret.append(send_sms(",".join(pns), sign_name, template_code, template_param))
    return ret


def send_sms(phone_number, sign_name, template_code, template_param=None):
    if isinstance(phone_number, (list, tuple, set)):
        return send_sms_batch_number(phone_number, sign_name, template_code, template_param)

    request = CommonRequest()
    request.set_accept_format('json')
    request.set_domain('dysmsapi.aliyuncs.com')
    request.set_method('POST')
    request.set_protocol_type('https')  # https | http
    request.set_version('2017-05-25')
    request.set_action_name('SendSms')

    request.add_query_param('RegionId', "cn-hangzhou")
    request.add_query_param('PhoneNumbers', phone_number)
    request.add_query_param('SignName', sign_name)
    request.add_query_param('TemplateCode', template_code)
    if template_param is not None:
        request.add_query_param('TemplateParam', template_param)
    response = get_client().do_action_with_exception(request)
    try:
        return json.loads(response)
    except Exception:
        return response
