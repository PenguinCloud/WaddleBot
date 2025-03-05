# encoding: utf-8
from __future__ import absolute_import, unicode_literals

import logging
import random
import time

from apiview.err_code import ErrCode
from apiview.exceptions import CustomError
from constance import config
from django.conf import settings

from .cache import VerifyCodeCount, VerifyCodeCache
from . import sms


class VerifyCode(object):
    def __init__(self, mobile, flag=''):
        self.mobile = mobile
        self.short_code = "%04d" % random.randint(1, 9999)
        self.long_code = "%06d" % random.randint(1, 999999)
        self.long_code_enable = False
        self.send_expiration_time = 0
        self.send_yy_expiration_time = 0
        self.expiration_time = 0
        self.sms_head = u"验证码(%s)" % self.long_code
        self.last_sms_index = -1
        self.gateway_num = None
        self.refresh_expiration_time()
        self.verify_times = 0
        self.flag = flag

    def refresh_send_expiration_time(self):
        self.verify_times = 0
        self.send_expiration_time = config.VERIFY_CODE_SEND_EXPIRE_SECONDS + int(time.time())

    def refresh_send_yy_expiration_time(self):
        self.verify_times = 0
        self.send_yy_expiration_time = config.VERIFY_CODE_SEND_EXPIRE_SECONDS + int(time.time())

    def refresh_expiration_time(self):
        self.expiration_time = config.VERIFY_CODE_SEND_EXPIRE_SECONDS + int(time.time())

    def get_sms_message(self):
        return "您的手机验证码为：%s。" % self.short_code

    def get_send_expiration(self):
        return self.send_expiration_time - int(time.time())

    def get_send_yy_expiration(self):
        return self.send_yy_expiration_time - int(time.time())

    def get_sms(self):
        return self.sms_head + config.VERIFY_CODE_SMS_CONTENT

    def check_sms(self, content):
        if content.startswith(self.sms_head):
            self.long_code_enable = True
            self.refresh_expiration_time()
            self.save()
            logging.getLogger('verify_code').info('check_sms ok:%s:%s', self.mobile, self.long_code)
            return True
        return False

    def get_verify_times(self):
        return self.verify_times

    def _verify(self, code):
        self.verify_times += 1
        self.save()
        return self.short_code == code or (self.long_code_enable and self.long_code == code)

    def save(self):
        VerifyCodeCache.set_code(self.mobile, self, self.flag)

    def delete(self):
        VerifyCodeCache.delete_code(self.mobile, self.flag)

    def count(self):
        return VerifyCodeCount.get(self.mobile) or 0

    def _send_sms(self):
        param = {settings.SMS_TEMPLATE_VCODE_PARAM: self.short_code}
        try:
            ret = sms.send_sms(self.mobile, settings.SMS_SIGNNAME_VCODE, settings.SMS_TEMPLATE_VCODE, param)
        except Exception:
            logging.getLogger('verify_code').exception('sms send fail:%s:%s', self.mobile, param)
            return False
        logging.getLogger('verify_code').info('sms send ok:%s:%s:%s', self.mobile, param, ret)
        return 'Code' in ret and ret['Code'] == 'OK'  # and 'Message' in ret and ret['Message'] == 'OK'

    def send(self):
        if self.get_send_expiration() > 0:
            raise CustomError(ErrCode.ERR_VCODE_WAIT, **self.data())
        if self.count() > config.VERIFY_CODE_MOBILE_COUNT:
            raise CustomError(ErrCode.ERR_VCODE_MOBILE_COUNT)
        if not self._send_sms():
            raise CustomError(ErrCode.ERR_VCODE_SEND_FAIL)
        VerifyCodeCount.incr(self.mobile)
        self.refresh_send_expiration_time()
        self.save()

    def verify(self, code):
        if not code:
            raise CustomError(ErrCode.ERR_COMMON_BAD_PARAM)

        pass_flag = self.mobile in config.VERIFY_CODE_WHITE_LIST_MOBILES.split(',')
        if settings.DEBUG:
            pass_flag = True
        if pass_flag and code == config.VERIFY_CODE_WHITE_LIST_CODE:
            self.delete()
            return True
        if self.send_expiration_time <= 0:
            raise CustomError(ErrCode.ERR_VCODE_EXPIRE)
        if self.get_verify_times() > config.VERIFY_CODE_MAX_TIMES:
            raise CustomError(ErrCode.ERR_USER_VCODE_MAX_TIMES)
        if not self._verify(code):
            raise CustomError(ErrCode.ERR_USER_VCODE_INVALID)
        self.delete()
        return True

    def data(self):
        ret = dict()
        if self.send_expiration_time <= 0:
            return ret
        ret['ttl'] = self.get_send_expiration()
        if self.gateway_num is not None:
            ret['long_code'] = self.long_code
            ret['sms_content'] = self.get_sms()
            ret['sms_num'] = self.gateway_num
        return ret

    @classmethod
    def get(cls, mobile, flag=''):
        ret = VerifyCodeCache.get_code(mobile, flag)
        if ret is None:
            ret = cls(mobile, flag)
        return ret
