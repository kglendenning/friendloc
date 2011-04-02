#!/usr/bin/env python
import pdb
from datetime import datetime, timedelta
import logging

from maroon import *

from base.splitproc import SplitProcess
from base.models import User, Tweet
from base.twitter import TwitterResource
from settings import settings


class CrawlProcess(SplitProcess):
    def __init__(self,db_name,**kwargs):
        SplitProcess.__init__(self, **kwargs)
        self.db_name = db_name
        self.waiting = set()

    def produce(self):
        Model.database = MongoDB(name=self.db_name,host=settings.mongo_host)
        for uid in User.next_crawl():
            if uid in self.waiting: continue # they are queued
            self.waiting.add(uid)
            yield uid

    def consume(self,items):
        for uid in items:
            self.waiting.remove(uid)

    def map(self,items):
        self.twitter = TwitterResource()
        Model.database = MongoDB(name=self.db_name,host=settings.mongo_host)
        #settings.pdb()

        for uid in items:
            try:
                user = User.get_id(uid)
                self.crawl(user)
                self.twitter.sleep_if_needed()
            except Exception as ex:
                if user:
                    logging.exception("exception for user %s"%user.to_d())
                else:
                    logging.exception("exception and user is None")
            yield uid
        print "slave is done"

    def crawl(self, user):
        logging.info("visiting %s - %s",user._id,user.screen_name)
        tweets = self.twitter.save_timeline(user._id, user.last_tid)
        if tweets:
            user.last_tid = tweets[0]._id
        now = datetime.utcnow()
        last = user.last_crawl_date if user.last_crawl_date is not None else datetime(2010,11,12)
        delta = now - last
        seconds = delta.seconds + delta.days*24*3600
        tph = (3600.0*len(tweets)/seconds + user.tweets_per_hour)/2
        user.tweets_per_hour = tph
        hours = min(settings.tweets_per_crawl/tph, settings.max_hours)
        user.next_crawl_date = now+timedelta(hours=hours)
        user.last_crawl_date = now
        user.save()

def crawl_once(region):
    proc = CrawlProcess(region, log_level=logging.INFO)
    #proc.run_single()
    proc.run()
