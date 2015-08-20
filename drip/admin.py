import base64
import json

from django import forms
from django.contrib import admin

from drip.models import Drip, SentDrip, QuerySetRule
from drip.drips import message_class_for
from drip.utils import get_user_model, configured_drip_classes, configured_message_classes


class QuerySetRuleInline(admin.TabularInline):
    model = QuerySetRule


class DripForm(forms.ModelForm):
    message_class = forms.ChoiceField(
        choices=((k, '%s (%s)' % (k, v)) for k, v in configured_message_classes().items())
    )
    drip_class = forms.ChoiceField(
        choices=((k, '%s (%s)' % (k, v)) for k, v in configured_drip_classes().items())
    )
    class Meta:
        model = Drip
        exclude = []


class DripAdmin(admin.ModelAdmin):
    list_display = ('name', 'enabled', 'message_class')
    inlines = [
        QuerySetRuleInline,
    ]
    form = DripForm

    av = lambda self, view: self.admin_site.admin_view(view)
    def timeline(self, request, drip_id, into_past, into_future):
        """
        Return a list of people who should get emails.
        """
        from django.shortcuts import render, get_object_or_404

        drip = get_object_or_404(Drip, id=drip_id)

        shifted_drips = []
        seen_users = set()
        for shifted_drip in drip.drip.walk(into_past=int(into_past), into_future=int(into_future)+1):
            shifted_drip.prune()
            shifted_drips.append({
                'drip': shifted_drip,
                'qs': shifted_drip.get_queryset().exclude(**{"%s__in" % shifted_drip.get_user_field(): seen_users})
            })
            seen_users.update(shifted_drip.get_queryset().values_list(shifted_drip.get_user_field(), flat=True))

        return render(request, 'drip/timeline.html', locals())

    def view_drip_email(self, request, drip_id, into_past, into_future, obj_id):
        from django.shortcuts import render, get_object_or_404
        from django.http import HttpResponse
        drip = get_object_or_404(Drip, id=drip_id)
        DripObjModel = drip.drip.query_model()
        drip_obj = get_object_or_404(DripObjModel, id=obj_id)
        user = getattr(drip_obj, drip.drip.get_user_field())

        drip_message = message_class_for(configured_message_classes(), drip.message_class)(drip.drip, user)
        # let message class render message
        content, mime = drip_message.get_message_content()
        return HttpResponse(content, content_type=mime)

    def build_extra_context(self, extra_context, object_id=None):
        from drip.utils import get_simple_fields
        extra_context = extra_context or {}
        if object_id:
            model = self.model.objects.get(pk=object_id).drip.query_model()
        else:
            model = get_user_model()
        extra_context['field_data'] = json.dumps(get_simple_fields(model))
        return extra_context

    def add_view(self, request, extra_context=None):
        return super(DripAdmin, self).add_view(
            request, extra_context=self.build_extra_context(extra_context))

    def change_view(self, request, object_id, extra_context=None):
        return super(DripAdmin, self).change_view(
            request, object_id, extra_context=self.build_extra_context(extra_context, object_id))

    def get_urls(self):
        from django.conf.urls import patterns, url
        urls = super(DripAdmin, self).get_urls()
        my_urls = patterns('',
            url(
                r'^(?P<drip_id>[\d]+)/timeline/(?P<into_past>[\d]+)/(?P<into_future>[\d]+)/$',
                self.av(self.timeline),
                name='drip_timeline'
            ),
            url(
                r'^(?P<drip_id>[\d]+)/timeline/(?P<into_past>[\d]+)/(?P<into_future>[\d]+)/(?P<obj_id>[\d]+)/$',
                self.av(self.view_drip_email),
                name='view_drip_email'
            )
        )
        return my_urls + urls
admin.site.register(Drip, DripAdmin)


class SentDripAdmin(admin.ModelAdmin):
    list_display = [f.name for f in SentDrip._meta.fields]
    ordering = ['-id']
admin.site.register(SentDrip, SentDripAdmin)
