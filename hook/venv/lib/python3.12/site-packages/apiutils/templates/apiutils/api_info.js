"use strict";
const request = require('./request')
const server = '{{server}}'; //服务地址

const ERROR_CODE = {
  {% for error_code in error_codes%}{{error_code.key}}: {{error_code.code}}{% if not forloop.last %},{% endif %} // {{error_code.message}}{% if not forloop.last %}
  {% endif %}{% endfor %}
}
{% for api in apis %}

// {{api.name}}
const {{ api.ul_name }} = function({% if api.params %}{
  {% for param in api.params %}{{ param.field }}{% if not forloop.last %},{% endif %} // {{ param.name }}{% if not forloop.last %}
  {% endif %}{% endfor %}
} = {}{% endif %}) {
  return request({
    server: server,
    path: '{{ api.url }}',
    method: '{{ api.suggest_method }}',
    data: {{% if api.params %}
      {% for param in api.params %}{{ param.field }}: {{ param.field}}{% if not forloop.last %},
      {% endif %}{% endfor %}
    {% endif %}},
    header: { 'Content-Type': '{{api.content_type}}' }
  })
}
{% endfor %}

module.exports = {
  ERROR_CODE: ERROR_CODE,
  {% for api in apis %}{{ api.ul_name }}: {{ api.ul_name }}{% if not forloop.last %},
  {% endif %}{% endfor %}
}
