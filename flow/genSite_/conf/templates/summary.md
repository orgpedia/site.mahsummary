# {{ site.title}}

**Date Range**: {{site.start_date_str}} - {{site.end_date_str}}


{% for (doc_type, docs) in depts.items() %}
## {{ doc_type }}
{% for doc in docs %}
- {{ doc.text }}\
  [{{doc.code}}.pdf]({{doc.url}})

{% endfor %}
{% endfor %}

*Archives of earlier summaries are available at http://mahsummary.orgpedia.in/en/archive.html*
