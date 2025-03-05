# encoding: utf-8
from __future__ import absolute_import, unicode_literals

import datetime

from apiview import cache


class VerifyCodeCount(cache.BaseCacheItem):
    _prefix = 'verify_code_count'

    @classmethod
    def get_prefix(cls):
        return '%s:%s' % (cls._prefix, datetime.datetime.now().strftime('%Y%m%d'))


class VerifyCodeCache(cache.BaseCacheItem):
    _prefix = 'verify_code'
    _expire_secs = 60 * 30

    @classmethod
    def get_key(cls, mobile, flag):
        return "%s:%s" % (flag, mobile)

    @classmethod
    def get_code(cls, mobile, flag=''):
        return cls.get(cls.get_key(mobile, flag))

    @classmethod
    def set_code(cls, mobile, code, flag='', ttl=None):
        return cls.set(cls.get_key(mobile, flag), code, ttl)

    @classmethod
    def ttl_code(cls, mobile, flag=''):
        return cls.ttl(cls.get_key(mobile, flag))

    @classmethod
    def delete_code(cls, mobile, flag=''):
        return cls.delete(cls.get_key(mobile, flag))
