from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)

@register.filter
def get_or_empty_string(dictionary, key):
    v = dictionary.get(key)
    if not v:
        return ""

    return v
