# Copyright 2013: James Tunnicliffe
#
# This file is part of Need Input.
#
# Need Input is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Need Input is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Need Input.  If not, see <http://www.gnu.org/licenses/>.

from django.conf import settings
from django.shortcuts import render_to_response
import imaplib
import os
import re
import requests
from BeautifulSoup import BeautifulSoup
from launchpadlib.launchpad import Launchpad
import urlparse
import threading
import Queue


def create_wi_list(text):
    work_items = []
    valid_states = ["TODO", "INPROGRESS", "POSTPONED"]  # "DONE" is left out - don't care about it!

    for line in text.splitlines():
        match = re.search("^(.*?)\\s*:\\s*(\\w+)\\s*$", line)
        if match and match.group(2) in valid_states:
            work_items.append((match.group(1), match.group(2)))

    return work_items


class GetStuff(threading.Thread):
    def __init__(self, queue, data):
        threading.Thread.__init__(self)
        self.queue = queue
        self.data = data

    def run(self):
        #TODO: There is a race condidion with LP thread startup.
        while True:
            try:
                target = self.queue.get(timeout=10)
            except Queue.Empty:
                return
            if isinstance(target, tuple):
                var = target[1]
                target = target[0]

            if target == "gmail":
                # Email
                mail = imaplib.IMAP4_SSL('imap.gmail.com')
                mail.login(settings.GMAIL_USER, settings.GMAIL_PASSWORD)
                mail.select("inbox")  # connect to inbox.
                result, data = mail.uid("search", None, "UnSeen")
                if len(data[0]):
                    result, data = mail.uid('fetch', ",".join(data[0].split()),
                            '(BODY.PEEK[HEADER.FIELDS (SUBJECT)] X-GM-THRID X-GM-MSGID)')

                self.data["emails"] = {}

                for thing in data:
                    if len(thing) == 2:
                        mail_id = hex(int(re.search(r"X-GM-THRID\s+(\d+)", thing[0]).group(1)))
                        self.data["emails"][mail_id] = (re.sub(r"[\n\r]", "", thing[1]),
                            "https://mail.google.com/mail/u/0/?shva=1#inbox/" + mail_id[2:])

            if target == "lp_bugs":
                # Bugs
                cachedir = os.path.join(settings.PROJECT_ROOT, ".launchpadlib/cache/")
                launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir)
                me = launchpad.people[settings.LP_USER]
                self.data["lp_bugs"] = []
                for bug in me.searchTasks(assignee=me):
                    self.data["lp_bugs"].append({
                        "title": re.search('"(.*)"', bug.title).group(1),
                        "url": bug.web_link,
                        "target": bug.bug_target_display_name,
                        "importance": bug.importance,
                        "status": bug.status
                    })

                bug_prio = {
                    "Undecided": 0,
                    "Critical": 1,
                    "High": 2,
                    "Medium": 3,
                    "Low": 4,
                    "Wishlist": 5,
                }

                self.data["lp_bugs"] = sorted(self.data["lp_bugs"], key=lambda bug: bug_prio[bug["importance"]])

            if target == "lp_reviews":
                # Reviews
                cachedir = os.path.join(settings.PROJECT_ROOT, ".launchpadlib/cache/")
                launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir)
                me = launchpad.people[settings.LP_USER]
                self.data["reviews"] = []
                for review in me.getRequestedReviews():
                    self.data["reviews"].append(review.web_link)

            if target == "lp_merges":
                cachedir = os.path.join(settings.PROJECT_ROOT, ".launchpadlib/cache/")
                launchpad = Launchpad.login_anonymously('just testing', 'production', cachedir)
                me = launchpad.people[settings.LP_USER]
                self.data["merge_proposals"] = []
                for mp in me.getMergeProposals():
                    self.data["merge_proposals"].append(mp.web_link)

            if target == "cards":
                # Cards
                jira_cards = requests.get(
                    "http://cards.linaro.org/rest/api/2/search?jql=assignee='%s'" %
                    settings.JIRA_LOGIN[0], auth=settings.JIRA_LOGIN)

                self.data["cards"] = []
                data = []
                if jira_cards.json["issues"]:
                    for issue in jira_cards.json["issues"]:
                        if "parent" in issue["fields"]:
                            parent = issue["fields"]["parent"]["key"], issue["fields"]["parent"]["fields"]
                        else:
                            parent = ""

                        data.append({
                            "name": issue["fields"]["summary"],
                            "url": "http://cards.linaro.org/browse/" + issue["key"],
                            "status": issue["fields"]["status"]["name"],
                            "priority": issue["fields"]["priority"]["name"],
                            "fix_versions": " ".join([v["name"] for v in issue["fields"]["fixVersions"]]),
                            "issue_type": issue["fields"]["issuetype"]["name"],
                            "parent": parent,
                            "key": issue["key"],
                        })

                # Sort the card data so it can be pretty-printed
                order = ["Roadmap Card", "Blueprint", "Sub-task"]
                for key in order:
                    for card in data:
                        if "Resolved" == card["status"]:
                            continue

                        if card["issue_type"] == key:
                            if card["parent"]:
                                found_parent = False
                                for i in range(0, len(self.data["cards"])):
                                    if self.data["cards"][i]["key"] == card["parent"][0]:
                                        found_parent = True
                                        break
                                if not found_parent:
                                    parent_card = {
                                        "name": "(" + card["parent"][1]["summary"] + ")",
                                        "url": "http://cards.linaro.org/browse/" + card["parent"][0],
                                        "status": card["parent"][1]["status"]["name"],
                                        "priority":  card["parent"][1]["priority"]["name"],
                                        "fix_versions": "?",
                                    }
                                    self.data["cards"].insert(i+1, parent_card)
                                    i += 1
                                self.data["cards"].insert(i+1, card)
                            else:
                                self.data["cards"].append(card)

                # Catch cards I didn't order
                for card in data:
                    if card["issue_type"] not in order:
                        self.data["cards"].append(card)

            if target == "blueprints":
                # Blueprints
                r = requests.get("https://blueprints.launchpad.net/~%s/+specs?role=assignee" % settings.LP_USER)
                soup = BeautifulSoup(r.text)
                junk = soup.findAll("span", {"class": "sortkey"})
                [thing.extract() for thing in junk]

                links = soup.findAll("a")
                self.data["lp_blueprints"] = []
                bp_links = []
                for link in links:
                    if not re.search("/\+spec/", link["href"]):
                        continue
                    if not re.search("^http", link["href"]):
                        link["href"] = urlparse.urljoin("https://blueprints.launchpad.net",
                                                        link["href"])
                        bp_links.append(link["href"])

                seen_links = {}
                for link in bp_links:
                    if link in seen_links:
                        continue
                    else:
                        seen_links[link] = True

                    self.queue.put(("bp_fetch", link))

            if target == "bp_fetch":
                link = var

                bp = requests.get(re.sub(r"https://blueprints.launchpad.net",
                                    r"https://api.launchpad.net/devel", link)).json

                if(bp["assignee_link"] ==
                    "https://api.launchpad.net/devel/~%s" % settings.LP_USER and
                   link not in settings.IGNORE["lp_bp"]):
                    self.data["lp_blueprints"].append({
                        "url": link,
                        "name": bp["title"],
                        "priority": bp["priority"],
                        "definition_status": bp["definition_status"],
                        "implementation_status": bp["implementation_status"],
                        "work_items": create_wi_list(bp["workitems_text"]),
                    })

            self.queue.task_done()


def home(request):
    queue = Queue.Queue()
    data = {}
    data["lp_blueprints"] = []
    tasks = ["gmail", "lp_bugs", "lp_reviews", "lp_merges", #"blueprints",
             "cards"]
    for task in tasks:
        queue.put(task)
        t = GetStuff(queue, data)
        t.setDaemon(True)
        t.start()

    queue.join()

    return render_to_response('home.html',
        {
            "lp_bp": data["lp_blueprints"],
            "lp_bugs": data["lp_bugs"],
            "jira_cards": data["cards"],
            "reviews": data["reviews"],
            "merge_proposals": data["merge_proposals"],
            "emails": data["emails"],
            "calendar": settings.CAL_EMBED
        })
