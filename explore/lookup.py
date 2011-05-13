#!/usr/bin/env python
import sys
sys.path.append("..")

import random
import itertools
import logging

from base.models import Edges, User, Tweets
from base.twitter import TwitterResource
from base.gisgraphy import GisgraphyResource
import base.utils as utils
from settings import settings
from base.splitproc import SplitProcess


class UsersToLookupFinder(SplitProcess):
    def __init__(self,db_name,**kwargs):
        SplitProcess.__init__(self, **kwargs)
        self.db_name = db_name
        self.chunk_lookup = _ChunckLookup(**kwargs)
        self.chunk_lookup.db_name = db_name

    def produce(self):
        return User.find(User.median_loc.exists(), fields=[], timeout=False)

    def startup(self):
        self.gis = GisgraphyResource()
        utils.use_mongo(self.db_name)
 
    def map(self,users):
        for user in users:
            logging.info("investigating %d",user._id)
            edges = Edges.get_id(user._id)
            tweets = Tweets.get_id(user._id,fields=['ats'])
            uids = set(itertools.chain(
                edges.friends or [],
                edges.followers or [],
                tweets.ats or []))
            if len(uids)>2000:
                chosen = random.sample(uids,2000)
                user = User.get_id(user._id)
                user.many_edges = True
                user.save()
                edges.lookups = chosen
                edges.save()
                yield set(chosen)
            else:
                yield uids

    def _filter_old_uids(self, uid_sets):
        logging.info("began to read old uids")
        done = set(u['_id'] for u in User.database.User.find(fields=[]))
        logging.info("read old uids")
        for s in uid_sets:
            new = s-done
            done.update(new)
            logging.info("queueing %d of %d users",len(new),len(s))
            yield new

    def consume(self, uid_sets):
        self.chunk_lookup.groups = utils.grouper(100,
            itertools.chain.from_iterable(
                self._filter_old_uids(uid_sets)
            ))
        self.chunk_lookup.run()


class _ChunckLookup(SplitProcess):
    def startup(self):
        self.twitter = TwitterResource()
        self.gis = GisgraphyResource()
        utils.use_mongo(self.db_name)

    def produce(self):
        return self.groups

    def map(self, chunks):
        for chunk in chunks:
            self.twitter.sleep_if_needed()
            users = filter(None,self.twitter.user_lookup(user_ids=list(chunk)))
            saved = 0
            for amigo in filter(None,users):
                if not amigo or amigo.protected: continue
                place = self.gis.twitter_loc(amigo.location)
                if not place:
                    continue
                amigo.geonames_place = place
                amigo.merge()
                saved +=1
            logging.info("saved %d of %d",saved,len(users))
            yield None


if __name__ == '__main__':
    proc = UsersToLookupFinder("usgeo",
            label='geolookup',
            log_level=logging.INFO,
            slaves=6,
            )
    proc.run()
