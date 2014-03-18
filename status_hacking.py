import ujson as json
import requests
import urllib
import local_settings as settings
import os.path
import time
import datetime

def download(url, filename):
    # TODO: Count returned cards Vs maxResults and if they are equal
    # try again with startAt set to start_index += maxResults
    # Probably should set maxResults to 1000 anyway...
    print url
    start_time = time.time()
    data = requests.get(url, auth=settings.JIRA_LOGIN).json()
    duration = time.time() - start_time
    print "Query took", duration, "seconds."

    if "errorMessages" in data:
        print data["errorMessages"]
        return {}

    with open(filename, "w") as f:
        json.dump(data, f)

    return data

def get_cards(get_update=False):
    filename = "query.json"
    url = 'https://cards.linaro.org/rest/api/2/search?'
    fields = ['summary', 'status', 'resolution', 'resolutiondate',
              'components', 'fixVersions']
    url += 'fields=' + ','.join(fields)
    url += '&maxResults=1000'
    url += '&jql='
    jql = 'project=CARD'

    if os.path.isfile(filename):
        print "Opening", filename
        with open(filename) as f:
            jira_cards = json.load(f)

        if get_update:
            print "Downloading update"
            # TODO: calculate update time based on age of "filename"
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

    return jira_cards


def add_card(card, cards, start_date, end_date):
    # Given a lump of data from Jira, insert data into nice dict.
    completion_date = None
    include = False
    if len(card["fields"]["fixVersions"]):
        for fixversion in card["fields"]["fixVersions"]:
            if "releaseDate" in fixversion:
                completion_date = datetime.datetime.strptime(
                    fixversion["releaseDate"], "%Y-%m-%d").date()
                if completion_date > start_date and completion_date < end_date:
                    include = True
                    break

    if card["fields"]["resolution"] and card["fields"]["resolutiondate"]:
        if not completion_date:
            completion_date = datetime.datetime.strptime(
                card["fields"]["resolutiondate"][:10], "%Y-%m-%d").date()
            if completion_date > start_date and completion_date < end_date:
                include = True

    if not include:
        return False

    cards["issues"][card["key"]] = {
        "name": card["fields"]["status"]["name"],
        "summary": card["fields"]["summary"],
        "url": "https://cards.linaro.org/browse/" + card["key"],
        "components": [],
    }

    for c in card["fields"]["components"]:
        cards["issues"][card["key"]]["components"].append(c["id"])

    if card["fields"]["resolution"]:
        cards["issues"][card["key"]]["resolution"] = {
                "name": card["fields"]["resolution"]["name"],
                "date": card["fields"]["resolutiondate"]
            }
    else:
        cards["issues"][card["key"]]["resolution"] = None

    return True


def organise_cards(jira_cards, start_date, end_date, component_filter=None,
                   status_filter=None):
    states = ["Admin",
              "Drafting",
              "Approved",
              "Scheduled",
              "Development",
              "Upstream Development",
              "Closing-out Review",
              "Closed",
              "Total"]

    cards = {
        "components": {},
        "issues": {},
        "summary": {},
        "states": states,
        "summary_table": [],
    }

    # Pick out components
    components = {}
    for card in jira_cards["issues"]:
        for target_component in card["fields"]["components"]:
            components[target_component["id"]] = target_component["name"]
            cards["components"][target_component["id"]] = \
                target_component["name"]

    # Pick out cards
    for component_id, component_name in components.iteritems():
        if component_filter and component_name != component_filter:
            continue
        states = {}
        for card in jira_cards["issues"]:
            for component in card["fields"]["components"]:
                if component["id"] == component_id:
                    if(status_filter and status_filter !=
                        card["fields"]["status"]["name"]):
                        continue

                    if add_card(card, cards, start_date, end_date):
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
    for id in cards["components"]:
        project_names.append((id, cards["components"][id]))
    project_names = sorted(project_names, key=lambda tup: tup[1])

    for id, name in project_names:
        cards["summary_table"].append([name])
        total = 0

        for state in cards["states"]:
            if state in cards["summary"][id]:
                value = cards["summary"][id][state]
                cards["summary_table"][-1].append(value)
                total += int(value)
            else:
                cards["summary_table"][-1].append("0")

        cards["summary_table"][-1].append(str(total))

    return cards


def print_summary(cards):
    for id, name in cards["components"].iteritems():
        print id, name
        print cards["summary"][id]
        for card_id, data in cards["issues"].iteritems():
            if id in data["components"]:
                print card_id, data

    for line in cards["summary_table"]:
        print line

def main():
    jira_cards = get_cards()
    start_date = datetime.date(2014,3,8)
    end_date = datetime.date(2014,9,14)
    cards = organise_cards(jira_cards, start_date, end_date)
    print_summary(cards)


if __name__ == "__main__":
    main()
