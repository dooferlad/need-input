import ujson as json
import json as slow_json
import requests
import urllib
import local_settings as settings
import os.path
import time
import datetime
#import cProfile
import pymongo

def download(url, filename, max_results=None):
    got_results = 0
    all_data = None
    print "Downloading card data"
    print url

    while max_results is None or got_results < max_results:
        fetch_url = url + "&startAt=%d" % got_results
        start_time = time.time()
        data = requests.get(fetch_url, auth=settings.JIRA_LOGIN)
        data = data.json()
        duration = time.time() - start_time
        print "Query took", duration, "seconds."

        if "errorMessages" in data:
            print data["errorMessages"]
            return {}

        got_results += len(data["issues"])

        if all_data is None:
            if max_results is None:
                max_results = int(data["total"])

            all_data = data.copy()
        else:
            # We know the structure of the data we are getting back, so we
            # do this rather than a more complex merge. We don't use any other
            # fields (at the moment), so we don't update them.
            all_data["issues"] += data["issues"]

        print "Got", got_results, "of", max_results

    with open(filename, "w") as f:
        json.dump(all_data, f)

    return all_data


def get_cards(client, get_update=False):
    filename = "query.json"
    url = 'https://cards.linaro.org/rest/api/2/search?'
    fields = ['summary', 'status', 'resolution', 'resolutiondate',
              'components', 'fixVersions', 'created', 'issuelinks', 'labels']
    url += 'fields=' + ','.join(fields)
    url += '&maxResults=100'
    url += '&expand=changelog'
    url += '&jql='
    jql = 'project=CARD'

    cards_db = client["roadmap"]

    if os.path.isfile(filename):
        print "Opening", filename
        with open(filename) as f:
            jira_cards = json.load(f)

        if get_update:
            print "Downloading update"
            # TODO: calculate update time based on age of "filename"
            # -- no - put in CouchDB! Keep an update time or something.
            jql += ' AND updated > -3d'
            url += urllib.quote_plus(jql)
            updates = download(url, "update.json")

            # Update jira_cards with data from the update call
            cards_by_key = {}
            for card in jira_cards["issues"]:
                cards_by_key[card["key"]] = card

            for card in updates["issues"]:
                print "Updating", card["key"]
                cards_by_key[card["key"]] = card

            # Now cards_by_key is the up-to-date database of everything we need
            # Note that we don't bother saving it because it will be put in a
            # database at some point, not stored as JSON and dictionaries.

            # Now to put back the data in the form we expect it. What fun!
            jira_cards["issues"] = []
            for index, card in cards_by_key.iteritems():
                jira_cards["issues"].append(card)

        with open(filename, "w") as f:
            json.dump(jira_cards, f)
    else:
        print "Downloading data"
        url += urllib.quote_plus(jql)
        jira_cards = download(url, filename)

    # TODO: Get rid of this JSON storage nonsense and just store in DB.
    # cards_db.find_one({"key": card["key"]) will return something to update or
    # Null, either way, overwrite with data from the card, keeping existing _id
    cards_db["jira_cards"].drop()
    cards_db["jira_cards"].insert(jira_cards["issues"])


def add_card(card, cards, start_date, end_date, include_changelog):
    # Given a lump of data from Jira, insert data into nice dict.
    completion_date = None
    include = False
    if len(card["fields"]["fixVersions"]):
        for fixversion in card["fields"]["fixVersions"]:
            if "releaseDate" in fixversion:
                completion_date = datetime.datetime.strptime(
                    fixversion["releaseDate"], "%Y-%m-%d").date()
                break

    if card["fields"]["resolution"] and card["fields"]["resolutiondate"]:
        if not completion_date:
            completion_date = datetime.datetime.strptime(
                card["fields"]["resolutiondate"][:10], "%Y-%m-%d").date()

    if completion_date is None:
        return False

    # If we haven't been given a start or end date, these assignments will
    # make sure that the None values are treated as always in range.
    if start_date is None:
        start_date = completion_date
    if end_date is None:
        end_date = completion_date

    if completion_date >= start_date and completion_date <= end_date:
        include = True

    if not include:
        return False

    try:
        completion_date.strftime("%Y-%m-%d")
    except AttributeError:
        completion_date = datetime.datetime.strptime(
                    "9999-01-01", "%Y-%m-%d").date()

    filtered_card = {
        "status": card["fields"]["status"]["name"],
        "summary": card["fields"]["summary"],
        "url": "https://cards.linaro.org/browse/" + card["key"],
        "components": [],
        "completion_date": completion_date.strftime("%Y-%m-%d"),
        "created": card["fields"]["created"],
        "links_in": [],
        "links_out": [],
        "key": card["key"],
        "labels": card["fields"]["labels"],
    }

    if include_changelog and "changelog" in card:
        filtered_card["changelog"] = card["changelog"]

    for c in card["fields"]["components"]:
        filtered_card["components"].append(c["id"])

    if card["fields"]["resolution"]:
        filtered_card["resolution"] = {
                "name": card["fields"]["resolution"]["name"],
                "date": card["fields"]["resolutiondate"]
            }
    else:
        filtered_card["resolution"] = None

    links = card["fields"].get("issuelinks")
    if links:
        for link in links:
            if "outwardIssue" in link:
                filtered_card["links_out"].append(link["outwardIssue"]["key"])
            if "inwardIssue" in link:
                filtered_card["links_out"].append(link["inwardIssue"]["key"])

    cards["issues"].append(filtered_card)
    return True


def organise_cards(client, start_date=None, end_date=None,
                   component_filter=None, status_filter=None,
                   include_changelog=False):
    states = ["Admin",
              "Drafting",
              "Approved",
              "Scheduled",
              "Development",
              "Upstream Development",
              "Closing-out Review",
              "Closed",]

    jira_cards = client["roadmap"]["jira_cards"]

    cards = {
        "components": [],
        "issues": [],
        "num_issues": 0,
        "summary": {},
        "states": states,
        "summary_table": [],
    }

    # Pick out components
    components = {}
    # for card in jira_cards.find():
    #     print "1", card["key"]
    #     for target_component in card["fields"]["components"]:
    #         if target_component["id"] not in components:
    #             components[target_component["id"]] = target_component["name"]
    #             cards["components"].append({
    #                 "id": target_component["id"],
    #                 "name": target_component["name"]
    #             })

    ids = jira_cards.distinct("fields.components.id")
    for id in ids:
        card = jira_cards.find_one({"fields.components.id": id})
        for component in card["fields"]["components"]:
            if component["id"] == id:
                components[id] = component["name"]
                cards["components"].append({
                    "id": id,
                    "name": component["name"],
                })

    # Pick out cards
    for component_id, component_name in components.iteritems():
        if component_filter and component_name != component_filter:
            continue
        states = {}
        for card in jira_cards.find({"fields.components.id": component_id}):
            for component in card["fields"]["components"]:
                if component["id"] == component_id:
                    if(status_filter and status_filter !=
                        card["fields"]["status"]["name"]):
                        continue

                    if add_card(card, cards, start_date, end_date,
                                include_changelog):
                        state_name = card["fields"]["status"]["name"]
                        if state_name in states:
                            states[state_name] += 1
                        else:
                            states[state_name] = 1

                            if state_name not in cards["states"]:
                                print "Unknown state found", state_name
                                cards["states"].append(state_name)

        cards["summary"][component_id] = states

    # Make a table that can be used to directly construct an
    # HTML table, summarising card states per team. Note that if
    # any filters have been used then this will also be filtered.
    project_names = []
    for component in cards["components"]:
        if component_filter and component["name"] != component_filter:
            continue
        project_names.append((component["id"], component["name"]))
    project_names = sorted(project_names, key=lambda tup: tup[1])

    for id, name in project_names:
        if component_filter and name != component_filter:
            continue
        cards["summary_table"].append([(id, name)])
        total = 0

        for state in cards["states"]:
            if state in cards["summary"][id]:
                value = cards["summary"][id][state]
                cards["summary_table"][-1].append((state, value))
                total += int(value)
            else:
                cards["summary_table"][-1].append((state, "0"))

        cards["summary_table"][-1].append(str(total))

    cards["num_issues"] = len(cards["issues"])

    # Add information about cycles with available data
    metrics = Metrics(cards, jira_cards, start_date, end_date)
    metrics.get_metrics()

    cards["sprint_data"] = []
    for sprint in metrics.sprint_data:
        if(len(cards["sprint_data"]) == 0 or
           sprint["end"].year != cards["sprint_data"][-1]["name"]):
            cards["sprint_data"].append({
                "name": sprint["end"].year,
                "sprints": [],
            })
        cards["sprint_data"][-1]["sprints"].append({
            "name": sprint["end"].month,
            "start": str(sprint["start"]),
            "end": str(sprint["end"]),
        })

    client["roadmap"].drop_collection("cards")
    cards_db = client["roadmap"]["cards"]
    cards_db.insert(cards)

    return cards


class CardInSprint:
    def __init__(self, sprint_start, sprint_end, card_start, card_end):
        self.sprint_start = datetime.datetime.combine(sprint_start,
                                                      datetime.time())
        self.sprint_end = datetime.datetime.combine(sprint_end,
                                                    datetime.time())
        # We get a date, which implies midnight. We want to include
        # all that day for the sprint end, so we add 1 to it and use
        # the appropriate inequality tests below.
        self.sprint_end += datetime.timedelta(days=1)
        self.card_start = card_start
        self.card_end = card_end

    @property
    def starts_in_sprint(self):
        return(self.sprint_start <= self.card_start and
               self.card_start < self.sprint_end)

    @property
    def covers_sprint(self):
        return(self.card_start < self.sprint_start and
               self.sprint_end <= self.card_end)

    @property
    def inside_sprint(self):
        return(self.sprint_start <= self.card_start and
               self.card_end < self.sprint_end)

    @property
    def ends_in_sprint(self):
        return(self.sprint_start <= self.card_end and
               self.card_end < self.sprint_end)

    @property
    def active_in_sprint(self):
        return(self.starts_in_sprint or self.covers_sprint or
               self.inside_sprint or self.ends_in_sprint)

    @property
    def before_or_during_sprint(self):
        return(self.card_start < self.sprint_end)

class Metrics():
    def __init__(self, cards, jira_cards, start_date, end_date):
        today = datetime.datetime.today()
        self.found_states = {}
        self.state_translation = {
            "Planning": "Drafting",
            "Delivered": "Closed",
            "Review": "Drafting",
            "Closing-review": "Closing-out Review",
        }

        self.cards = cards
        oldest_card_date = today
        newest_card_date = today

        for card in self.cards["issues"]:
            t = datetime.datetime.strptime(card["completion_date"], "%Y-%m-%d")
            if t.year == 9999:
                # No completion date is encoded with year 9999. Ignore them.
                continue
            oldest_card_date = min(t, oldest_card_date)
            newest_card_date = max(t, newest_card_date)

            if "changelog" in card:
                for step in card["changelog"]["histories"]:
                    t = datetime.datetime.strptime(
                            step["created"][:16], "%Y-%m-%dT%H:%M")
                    oldest_card_date = min(t, oldest_card_date)
                    newest_card_date = max(t, newest_card_date)

        if start_date is not None:
            self.start_date = max(start_date, oldest_card_date.date())
        else:
            self.start_date = oldest_card_date.date()

        if end_date is not None:
            self.end_date = min(end_date, newest_card_date.date())
        else:
            self.end_date = newest_card_date.date()

    def get_metrics(self):
        """Calculate a bunch of metrics about the cards

        Late and on time (% and count)
        Number of cards in each state (Drafing / Scheduled etc)
        Average number of cards in each state over <duration>
        Average time cards in each state
        """

        #headings = ["Component Name", "Total Cards", "Late Cards"]
        #headings += self.cards["states"]
        #for name in headings:
        #    print "%20s," % name,
        #print ""

        found_crap = {}

        for component in self.cards["components"]:
            #if component_name != "LAVA":
            #    continue

            # Create structure of:
            # self.sprint_data = [
            #     {
            #         "start": cycle_start,
            #         "end": cycle_end,
            #         "counts": {
            #             <state_name>: <card_count>,
            #         },
            #         "times": {
            #             <state_name>: <time spent in this state>,
            #         },
            #         "deltas": {
            #             "start": <delta start>
            #             "end": <delta end>
            #             "count": {<state_name>: <card_count>}
            #         },
            #     }...
            # ]
            self.sprint_data = []
            month_offset = 0
            year_offset = 0
            while True:

                m = (self.start_date.month - 1 + month_offset) % 12 + 1
                y = (self.start_date.month - 1 + month_offset) / 12 +\
                    self.start_date.year
                #print self.start_date.month, month_offset, m, y
                t = datetime.date(y, m, self.start_date.day)
                month_offset += 1

                cycle_start, cycle_end = self.get_cycle_dates(t)
                if cycle_start > self.end_date:
                    break

                #print cycle_start, cycle_end, self.end_date

                self.sprint_data.append({
                    "start": cycle_start,
                    "end": cycle_end,
                    "counts": {},
                    "times": {},
                    "deltas": [],
                    "time_until_now": {},
                    "total_cards": 0,
                    "late_cards": 0,
                    "index": month_offset,
                })

                if False:
                    # TODO: Clear this out to an archive somewhere
                    # Logic from initial card metrics hack. Don't use for web.
                    delta_time = cycle_start
                    while delta_time <= cycle_end:
                        delta_end = delta_time + datetime.timedelta(days=1)
                        self.sprint_data[-1]["deltas"].append({
                            "start": delta_time,
                            "end": delta_end,
                            "counts": {}
                        })
                        delta_time = delta_end

                    for state in self.cards["states"]:
                        self.sprint_data[-1]["counts"][state] = 0
                        self.sprint_data[-1]["times"][state] = datetime.timedelta()
                        self.sprint_data[-1]["time_until_now"][state] = datetime.timedelta()
                        for delta in self.sprint_data[-1]["deltas"]:
                            delta["counts"][state] = 0

            if False:
                # TODO: Clear this out to an archive somewhere
                # Logic from initial card metrics hack. Don't use for web.
                for card in self.cards["issues"]:
                    if component["id"] in card["components"]:
                        if "changelog" not in card:
                            continue
                        self.card_metrics(card)

            # TODO: Clear this out to an archive somewhere
            # Logic from initial card metrics hack. Don't use for web.
            #self._print_stats(component["name"])

        if len(self.found_states.keys()):
            print "Unhandled states:"
            for key in self.found_states.keys():
                print key

    def _print_stats(self, component_name):
        print "-" * 10, component_name, "-" * 10
        for sprint in self.sprint_data:
            print sprint["start"], "to", sprint["end"]
            print " Late:", sprint["late_cards"]
            for state, count in sprint["counts"].iteritems():
                print "  %20s %3d" % (state, count),
                if state in self.cards["states"] and sprint["total_cards"]:
                    days = sprint["times"][state].total_seconds() /60/60/24
                    average = days/sprint["total_cards"]

                    days = sprint["time_until_now"][state].total_seconds() /60/60/24
                    average_tun = days/sprint["total_cards"]
                else:
                    average = 0
                    average_tun = 0
                #print "%5.2f" % average,

                sprint_duration = (sprint["end"] - sprint["start"]).days + 1
                daily_average = average / sprint_duration
                #print sprint_duration,
                print "%5.2f" % daily_average,
                print "%6.2f" % average_tun,

                state_count = 0
                delta_count = 0
                for delta in sprint["deltas"]:
                    delta_count += 1
                    state_count += delta["counts"][state]

                #print "%3d, %2d" % (state_count, delta_count),
                #print "%5.2f" % (float(state_count) / delta_count)
                print ""

            print ""

    def card_metrics(self, card):
        today = datetime.datetime.today()
        self.last_change = datetime.datetime.strptime(
            card["created"][:16], "%Y-%m-%dT%H:%M")
        self.last_state = "Drafting"

        if self.last_change.date() < self.start_date:
            # Ignore cards that didn't exist before our start date.
            return

        self.card_sprint_state = []
        for index in range(len(self.sprint_data)):
            self.card_sprint_state.append({
                "first_fix_version": None,
                "last_fix_version": None,
                "active": False
            })

        #print "-" * 10, card["url"], "-" * 10

        for step in card["changelog"]["histories"]:
            self.state_at_start_of_change = self.last_state
            for change in step["items"]:
                change_date = datetime.datetime.strptime(
                        step["created"][:16], "%Y-%m-%dT%H:%M")

                if change_date.date() < self.start_date:
                    # Ignore all changes before given start date...
                    continue

                to_state = change["toString"]

                if change["field"] == "status":
                    if to_state in self.state_translation:
                        to_state = self.state_translation[to_state]

                    if self.last_state not in self.cards["states"]:
                        # Ignore states (don't total the time even)
                        # that are obsolete.
                        self.found_states[self.last_state] = 1
                        self.last_state = to_state
                        continue

                    self._card_metrics_sprints_state(change_date, card)

                    self.last_change = change_date
                    self.last_state = to_state

                if change["field"] == "Fix Version":
                    self._card_metrics_sprints_late(change_date, to_state)

        # The last bit of data is the current card state...
        if card["status"] != "Closed":
            self._card_metrics_sprints_state(today, card)
        else:
            self._card_metrics_sprints_state(self.last_change, card)
        self._card_metrics_late_finish_card(card)

    def _card_metrics_sprints_state(self, change_date, card):
        in_state_time = change_date - self.last_change

        for sprint in self.sprint_data:
            card_in_sprint = CardInSprint(sprint["start"],
                                sprint["end"],
                                self.last_change,
                                change_date)

            if card_in_sprint.active_in_sprint:
                self._card_metrics_state(card_in_sprint,
                                         in_state_time,
                                         sprint,
                                         change_date)

                self.card_sprint_state[sprint["index"]]["active"] = True

                sprint["counts"][self.last_state] += 1
                sprint["total_cards"] += 1

    def _card_metrics_sprints_late(self, change_date, fix_version):

        for sprint in self.sprint_data:
            card_in_sprint = CardInSprint(sprint["start"],
                                sprint["end"],
                                self.last_change,
                                change_date)

            if card_in_sprint.before_or_during_sprint:
                self._card_metrics_late(sprint, fix_version)

    def _card_metrics_state(self, card_in_sprint, in_state_time, sprint,
                            change_date):
        if card_in_sprint.inside_sprint:
            sprint["times"][self.last_state] += in_state_time
            sprint["time_until_now"][self.last_state] += in_state_time
        elif card_in_sprint.covers_sprint:
            cycle_duration = card_in_sprint.sprint_end - card_in_sprint.sprint_start
            sprint["times"][self.last_state] += cycle_duration

            tun = card_in_sprint.sprint_end - self.last_change
            sprint["time_until_now"][self.last_state] += tun
        elif card_in_sprint.starts_in_sprint:
            time_active_in_sprint = card_in_sprint.sprint_end - self.last_change
            sprint["times"][self.last_state] += time_active_in_sprint
            sprint["time_until_now"][self.last_state] += time_active_in_sprint
        elif card_in_sprint.ends_in_sprint:
            time_active_in_sprint = change_date - card_in_sprint.sprint_start
            sprint["times"][self.last_state] += time_active_in_sprint

            tun = change_date - self.last_change
            sprint["time_until_now"][self.last_state] += tun

    def _card_metrics_late(self, sprint, fix_version):
        if fix_version is None:
            return

        first_fix_version = \
            self.card_sprint_state[sprint["index"]]["first_fix_version"]

        if(not first_fix_version or
           self.state_at_start_of_change == "Drafting"):
            if fix_version == "ONGOING":
                first_fix_version = datetime.datetime(3000, 1, 1)
            else:
                try:
                    first_fix_version = datetime.datetime.strptime(
                        fix_version, "%Y.%m")
                except ValueError:
                    first_fix_version = None

        if self.state_at_start_of_change != "Drafting":
            # Cards in Drafting just reset the first_fix_version

            if fix_version == "ONGOING":
                last_fix_version = datetime.datetime(3000, 1, 1)
            else:
                try:
                    last_fix_version = datetime.datetime.strptime(
                        fix_version, "%Y.%m")
                except ValueError:
                    last_fix_version = None
        else:
            last_fix_version = first_fix_version

        self.card_sprint_state[sprint["index"]]["first_fix_version"] = \
            first_fix_version
        self.card_sprint_state[sprint["index"]]["last_fix_version"] = \
            last_fix_version

        #print self.state_at_start_of_change, first_fix_version, last_fix_version

    def _card_metrics_late_finish_card(self, card):
        if self.last_state in ["Drafting", "Upstream Development"]:
            # Cards in Drafting can not be late
            # Don't track late for upstream dev.
            return

        for sprint in self.sprint_data:
            if not self.card_sprint_state[sprint["index"]]["active"]:
                # Skip cards that weren't active during the sprint
                continue

            first_fix_version = \
                self.card_sprint_state[sprint["index"]]["first_fix_version"]
            last_fix_version = \
                self.card_sprint_state[sprint["index"]]["last_fix_version"]

            if first_fix_version and not last_fix_version:
                sprint["late_cards"] += 1
                #print "#", card["url"], first_fix_version, last_fix_version
            elif(first_fix_version and last_fix_version and
                 last_fix_version > first_fix_version):
                sprint["late_cards"] += 1
                #print ">", card["url"], first_fix_version, last_fix_version

    def get_cycle_dates(self, ref_date=datetime.datetime.today().date()):
        # Rewind to start of month
        one_day =  datetime.timedelta(1)
        last_day = datetime.date(ref_date.year, ref_date.month, 1)
        thursdays_found = 0
        while True:
            if last_day.weekday() == 3:
                thursdays_found += 1

                if thursdays_found == 4:
                    break

            last_day += one_day

        if ref_date.month == 1:
            first_day = datetime.date(ref_date.year-1, 12, 1)
        else:
            first_day = datetime.date(ref_date.year, ref_date.month-1, 1)

        fridays_found = 0
        while True < 4:
            if first_day.weekday() == 4:
                fridays_found += 1

                if fridays_found == 4:
                    break

            first_day += one_day

        return first_day, last_day

def print_summary(cards):
    # for id, name in cards["components"].iteritems():
    #     print id, name
    #     print cards["summary"][id]
    #     for card_id, data in cards["issues"].iteritems():
    #         if id in data["components"]:
    #             print card_id, data

    for line in cards["summary_table"]:
        print line


def main():
    connect_count = 0

    while True:
        try:
            client = pymongo.MongoClient()
            print "Connected!"
            break
        except pymongo.errors.ConnectionFailure:
            connect_count += 1
            if connect_count < 60:
                print "Waiting for DB to start"
                time.sleep(1)
            else:
                exit(1)

    #get_cards(client, get_update=False)
    start_date = datetime.date(2000,1,1)
    end_date = datetime.date(3000,1,1)

    organise_cards(client, start_date, end_date)

    #start_date = datetime.date(2014,1,1)
    #end_date = datetime.date(3014,3,28)

    #metrics = Metrics(cards, jira_cards, start_date, end_date)
    #metrics.get_metrics()
    #print_summary(cards)


if __name__ == "__main__":
    main()
