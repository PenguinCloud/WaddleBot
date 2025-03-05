# 接口文档

## 服务地址

`{{server}}`

## 错误码列表

| 标识 | 编码 | 描述 |
| ---- | ---- | ---- |
{% for error_code in error_codes %}| `{{error_code.key}}` | `{{error_code.code}}` | {{error_code.message}} |
{% endfor %}


## 接口列表

{% for api in apis %}
### {{api.name}}

请求接口: [`{{ api.url }}`]({{ server }}{{ api.url }})

{% if api.params %}
参数列表：

| 字段名 | 说明 | 类型 | 是否必填 | 默认值 | 其他说明 |
| ---- | ---- | ---- | ---- | ---- | ---- |
{% for param in api.params %}| {% if param.required %}**`{{ param.field }}`**{% else %}`{{ param.field }}`{% endif %} | {{ param.name }} | {{ param.type }} | {% if param.required %}是{% else %}否{% endif %} | {% if param.default and param.default != '<empty>' %}{{ param.default }}{% else %}{{ param.omit }}{% endif %} | {{ param.info }} |
{% endfor %}{% endif %}

{% if api.return_simple %}
返回样例：

```
{{ api.return_simple|safe }}
```
{% endif %}
{% if api.return_info %}
返回说明：

```
{{ api.return_info|safe }}
```
{% endif %}
{% endfor %}
