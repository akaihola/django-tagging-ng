from django.contrib import admin
from tagging.models import Tag, TaggedItem, Synonym
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.utils.translation import ugettext as _, ugettext_lazy
from django.core.urlresolvers import reverse
from tagging import settings
from tagging.forms import TagAdminForm

admin.site.register(TaggedItem)


class JoinActionMixin(object):
    """Custom admin action for joining tags

    This works with Django revisions <=12523 or after #12962 is fixed
    """
    actions = ['join_tags']

    def join_tags(self, request, queryset):
        """An action which joins selected tags as synonyms.

        This action first displays a confirmation page which shows all the tags
        to be joined and prompts the user to select the tag which will have the
        rest of those tags as synonyms.

        Next, it performs the join redirects back to the change list.
        """
        opts = self.model._meta
        app_label = opts.app_label

        if request.POST.get('post'):
            # The user has already confirmed the join.  Do the join and return
            # a None to display the change list view again.  The queryset needs
            # to be sorted so that the selected tag is first and synonyms
            # follow.
            tag_and_synonyms = sorted(
                queryset, key=lambda tag: tag.pk != int(request.POST['tag']))
            Tag.objects.join(tag_and_synonyms)
            self.message_user(
                request,
                _('Successfully joined %d tags.') % len(tag_and_synonyms))
            # Return None to display the change list page again.
            return None

        context = {
            'app_label': app_label,
            'title': _('Select main tag'),
            'queryset': queryset,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }

        # Display the confirmation and tag selection page
        return render_to_response(
            'admin/tagging/tag/join_confirmation.html',
            context,
            context_instance=RequestContext(request))

    join_tags.short_description = ugettext_lazy(
        'Join selected tags as synonyms of one tag')


def _synonyms(tag):
    return ', '.join(s.name for s in tag.synonyms.all())
_synonyms.short_description = _('synonyms')

if settings.MULTILINGUAL_TAGS:
    import multilingual

    def _name(tag):
        return tag.name_any
    _name.short_description = _('name')

    def _synonyms(tag):
        return ', '.join(s.name for s in tag.synonyms.all())
    _synonyms.short_description = _('synonyms')

    def _translations(tag):
        return ', '.join(s.name for s in tag.translations.all())
    _translations.short_description = _('translations')

    class TagAdmin(multilingual.ModelAdmin, JoinActionMixin):
        form = TagAdminForm
        list_display = (_name, _synonyms, _translations)
        search_fields = ('name', 'synonyms__name', 'translations__name')

    _synonym_tag_name = 'name_any'
else:
    class TagAdmin(admin.ModelAdmin, JoinActionMixin):
        form = TagAdminForm
        list_display = ('name', _synonyms)
        search_fields = ('name', 'synonyms__name')

    _synonym_tag_name = 'name'


admin.site.register(Tag, TagAdmin)

def _tag_name(synonym):
    return '<a href="%s">%s</a>' % (
        reverse('admin:tagging_tag_change', args=(synonym.tag.id,)),
        getattr(synonym.tag, _synonym_tag_name)
    )
_tag_name.short_description = _('tag')
_tag_name.allow_tags = True

admin.site.register(Synonym,
    list_display = ('name', _tag_name),
    search_fields = ('name',),
)

