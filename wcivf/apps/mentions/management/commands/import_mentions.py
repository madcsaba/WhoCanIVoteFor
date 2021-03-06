from django.core.management.base import BaseCommand

import requests

from mentions.models import Mention


class Command(BaseCommand):
    def handle(self, **options):
        url = "https://www.electionmentions.com/api/stream?since=2016-01-01"
        req = requests.get(url)
        results = req.json()

        for mention in results['stream_items']:
            if not mention['quote']:
                continue
            if "http://www.newstatesman.com/" in mention['url']:
                continue

            mention_obj, created = Mention.objects.update_or_create_from_em(
                mention)
            if created:
                print("Added new mention: {0}".format(mention['title']))
