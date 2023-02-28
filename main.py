from datetime import datetime
import math
import json
import pause
from pprint import pprint
import praw
import requests
import time
from RSSParser import find_newest_headline


def load_config(config_file):
    # Loads the config file
    try:
        with open(config_file) as json_data_file:
            config = json.load(json_data_file)
            return config['credentials'], config['subreddits']
    except Exception as e:
        print(f'Error loading {config_file}: {str(e)}')


def load_db(filename):
    # Loads the database file
    try:
        with open(filename) as file:
            return json.load(file)
    except Exception as e:
        print(f'Error loading {filename}: {str(e)}')
        print(f'Creating new {filename} file...')
        return {}


class RedditBot:
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) " \
                 "Chrome/108.0.0.0 Safari/537.36 OPR/94.0.0.0"

    def __init__(self):
        # Initializes db dictionary, sets self.db
        self.db = load_db('db.json')
        # Loads config file, sets self.credentials and self.sub_list
        self.credentials, self.sub_list = load_config('config.json')
        print("Config List:", end=' ')
        pprint(self.sub_list)
        # Initializes reddit praw object
        self.reddit = praw.Reddit(username = self.credentials['user'],
                                password = self.credentials['password'],
                                client_id = self.credentials['client_id'],
                                client_secret = self.credentials['client_secret'],
                                user_agent = "Subreddit-News:V1.0 by /u/GeoWa")

    def update_db(self, filename):
        with open(filename, 'w') as file:
            json.dump(self.db, file, indent=4)

    def rss_request(self, url, key):
        try:
            resp = requests.get(url, headers={
                'User-Agent': self.user_agent,
                'If-Modified-Since': self.db[key]["Last_Modified"],
                'If-None-Match': self.db[key]["ETag"]
            })
            if resp.status_code == 200:
                self.db[key]["Last_Modified"] = resp.headers['Last-Modified'] if 'Last-Modified' in resp.headers else None
                self.db[key]["ETag"] = resp.headers['ETag'] if 'ETag' in resp.headers else None
                return resp.text
            elif resp.status_code == 304:
                return None
        except Exception as e:
            print(f'Error requesting {url}: {str(e)}')

    def post_to_subreddit(self, sub_name, title, link, flair_text=None):
        # Posts to subreddit
        try:
            subreddit = self.reddit.subreddit(sub_name)
            if flair_text:
                # Find flair_id
                flair_choices = list(subreddit.flair.link_templates.user_selectable())
                for flair in flair_choices:
                    if flair["flair_text"] == flair_text:
                        subreddit.submit(title=title, url=link, resubmit=False, flair_id=flair["flair_template_id"])
                        print(f"Posted to {sub_name} with preset flair {flair_text}")
                        return
                # Use editable flair if no pre-defined flair found
                for flair in flair_choices:
                    if flair['flair_text_editable']:
                        subreddit.submit(title=title, url=link, resubmit=False,
                                        flair_id=flair["flair_template_id"], flair_text=flair_text)
                        print(f"Posted to {sub_name} with custom flair {flair_text}")
                        return
                # Use default flair if no editable flair found
                subreddit.submit(title=title, url=link, resubmit=False)
                print(f"Posted to {sub_name}, flair_text not found")
            else:
                subreddit.submit(title=title, url=link, resubmit=False)
                print(f"Posted to {sub_name}")
        except Exception as e:
            print(f'Error posting to {sub_name}: {str(e)}')

    # Main Program Loop
    def main_loop(self):
        while True:
            print("Starting RSS feed...")

            # next_update is the time in seconds until the next update
            next_update = math.inf
            for sub_info in self.sub_list:
                print(f"Checking r/{sub_info['subreddit_name']} with {sub_info['rss_url']}...")
                key = sub_info['subreddit_name'] + sub_info['rss_url']
                if key not in self.db:
                    self.db[key] = {'Last_Modified': None, 'ETag': None}
                    response_text = self.rss_request(sub_info['rss_url'], key)
                    title, link, guid = find_newest_headline(response_text)
                    print("New story found! Making reddit post...")
                    self.post_to_subreddit(sub_info['subreddit_name'], title, link,
                                           sub_info['flair'] if 'flair' in sub_info else None)
                    new_update = math.ceil(time.time()) + sub_info['delay']
                    self.db[key].update({'Last_Id': guid, 'Update_Time': new_update})
                    if new_update < next_update:
                        next_update = new_update
                elif self.db[key]['Update_Time'] <= math.ceil(time.time()):
                    response_text = self.rss_request(sub_info['rss_url'], key)
                    if not response_text:
                        print("No new data from RSS feed")
                        new_update = int(time.time()) + 3600
                        next_update = new_update if new_update < next_update else next_update
                        self.db[key]['Update_Time'] = new_update
                        continue
                    title, link, guid = find_newest_headline(response_text)
                    if self.db[key]['Last_Id'] == guid:
                        print("No new stories since last check")
                        new_update = int(time.time()) + 3600
                        self.db[key]['Update_Time'] = new_update
                    else:
                        print("New story found! Making reddit post...")
                        self.post_to_subreddit(sub_info['subreddit_name'], title, link,
                                               sub_info['flair'] if 'flair' in sub_info else None)
                        new_update = int(time.time()) + sub_info['delay']
                        self.db[key].update({'Last_Id': guid, 'Update_Time': new_update})
                    if new_update < next_update:
                        next_update = new_update
                else:
                    if self.db[key]['Update_Time'] < next_update:
                        next_update = self.db[key]['Update_Time']
            # Update db.json
            print("Updating db.json...")
            self.update_db('db.json')
            # Wait until next update
            print(f"Next update at {datetime.fromtimestamp(next_update)}")
            pause.until(next_update)


if __name__ == "__main__":
    bot = RedditBot()
    bot.main_loop()
