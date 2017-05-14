import requests

from django.conf import settings
from django.http import HttpResponseRedirect
from django.core.cache import cache

from notifications.forms import PostcodeNotificationForm
from core.models import log_postcode
from ..models import PostElection, InvalidPostcodeError


class ElectionNotificationFormMixin(object):
    notification_form = PostcodeNotificationForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == 'POST':
            context['notification_form'] = self.notification_form(
                self.request.POST)
        else:
            context['notification_form'] = self.notification_form()
        return context

    def save_postcode_to_session(self, postcode):
        notification_for_postcode = self.request.session.get(
            'notification_for_postcode', [])
        notification_for_postcode.append(postcode)
        self.request.session['notification_for_postcode'] = \
            notification_for_postcode
        self.request.session.modified = True

    def post(self, request, *args, **kwargs):
        if 'form_name' in request.POST:
            if request.POST['form_name'] == "postcode_notification":
                form = self.notification_form(request.POST)
                if form.is_valid():
                    form.save()
                    self.save_postcode_to_session(
                        form.cleaned_data['postcode'])
                    url = request.build_absolute_uri()
                    return HttpResponseRedirect(url)
                else:
                    return self.render_to_response(self.get_context_data())
        return super().post(request, *args, **kwargs)


class PostcodeToPostsMixin(object):
    def get(self, request, *args, **kwargs):
        try:
            context = self.get_context_data(**kwargs)
        except InvalidPostcodeError:
            return HttpResponseRedirect(
                '/?invalid_postcode=1&postcode={}'.format(
                    self.postcode
                ))
        return self.render_to_response(context)

    def postcode_to_posts(self, postcode):
        key = "upcoming_elections_{}".format(postcode)
        results_json = cache.get(key)
        if not results_json:
            url = '{0}/api/elections?postcode={1}&future=1'.format(
                settings.EE_BASE,
                postcode
            )
            req = requests.get(url)

            # Don't cache bad postcodes
            if req.status_code != 200:
                raise InvalidPostcodeError(postcode)

            results_json = req.json()['results']
            cache.set(key, results_json)

        all_posts = []
        all_elections = []
        for election in results_json:
            if election['group_type'] in ['organisation', 'election']:
                continue

            # Convert an EE election dict in to a YNR ID
            post_id = ":".join([
                election['division']['division_type'],
                election['division']['official_identifier'].split(':')[-1]
            ])

            all_posts.append(post_id)
            all_elections.append(election['group'])

        pes = PostElection.objects.filter(
            post__ynr_id__in=all_posts,
            election__slug__in=all_elections)
        pes = pes.select_related('post')
        pes = pes.select_related('election')
        pes = pes.select_related('election__voting_system')
        pes = pes.select_related('election')  # <- Better safe (x2) than sorry?
        pes = pes.prefetch_related('husting_set')
        pes = pes.order_by(
            'election__election_date',
            'election__election_weight'
        )
        return pes


class PollingStationInfoMixin(object):
    def get_polling_station_info(self, postcode):
        key = "pollingstations_{}".format(postcode)
        info = cache.get(key)
        if info:
            return info

        info = {}
        base_url = settings.WDIV_BASE + settings.WDIV_API
        url = "{}/postcode/{}.json?auth_token={}".format(
            base_url,
            postcode,
            getattr(settings, 'WDIV_API_KEY', 'DCINTERNAL-WHO')
        )
        try:
            req = requests.get(url)
        except:
            return info
        if req.status_code != 200:
            return info
        info.update(req.json())
        cache.set(key, info)
        return info


class LogLookUpMixin(object):
    def log_postcode(self, postcode):
        kwargs = {
            'postcode': postcode,
        }
        kwargs.update(self.request.session['utm_data'])
        log_postcode(kwargs)
