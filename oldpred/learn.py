import logging
from bisect import bisect

import numpy

from settings import settings
from base.models import *
from base.utils import *


def learn_user_model(key='50'):
    use_mongo('usgeo')
    logging.info('started %s',key)
    Trainer().train(key)
    logging.info('saved %s',key)

def build_user_model():
    Trainer().reduce()


class Trainer():
    def __init__(self):
        self.bins = 10**numpy.linspace(0,1,11)
        self.buckets = settings.fol_count_buckets
        self.power = numpy.zeros((16,self.buckets,len(self.bins)-1), numpy.int)
        self.inner = numpy.zeros((16,self.buckets), numpy.int)
        self.total = numpy.zeros_like(self.inner)
        self.a = numpy.zeros_like(self.inner, numpy.float)
        self.b = numpy.zeros_like(self.a)

    def train(self, key):
        users = User.find(User.mod_group == int(key))
        for user in users:
            self.train_user(user)
        result = self.to_d('inner', 'power', 'total')
        write_json([result], "data/model%s"%key)

    def train_user(self,me):
        tweets = Tweets.get_id(me._id,fields=['ats'])
        edges = Edges.get_id(me._id)
        ats = set(tweets.ats or [])
        frds = set(edges.friends or [])
        fols = set(edges.followers or [])
        
        group_order = (ats,frds,fols)
        def _group(uid):
            #return 7 for ated rfrd, 4 for ignored jfol
            return sum(2**i for i,s in enumerate(group_order) if uid in s)

        lookups = edges.lookups if edges.lookups else list(ats|frds|fols)
        #get the users - this will be SLOW
        amigos = User.find(
            User._id.is_in(lookups) & User.geonames_place.exists(),
            fields =['gnp','folc','prot'],
            )
        for amigo in amigos:
            kind = _group(amigo._id) + (8 if amigo.protected else 0)
            self.add_edge(me.median_loc, amigo, kind)

    def add_edge(self, mloc, user, kind):
        gnp = user.geonames_place.to_d()
        dist = coord_in_miles(mloc,gnp)/gnp['mdist']

        folc = max(user.followers_count,1)
        bits = min(self.buckets-1, int(math.log(folc,4)))
        self.total[kind,bits]+=1
        
        if dist<1:
            self.inner[kind,bits]+=1
        else:
            bin = bisect(self.bins,dist)-1
            if bin < len(self.bins)-1:
                self.power[kind,bits,bin]+=1

    def reduce(self):
        input_keys = 'inner','power','total'
        for d in read_json("model"):
            for k in input_keys:
                getattr(self,k).__iadd__(d[k])
        settings.pdb()
        #HACK: we set this one value because of one noisy outlier
        self.power[12,7,7]+=1
        #merge tiny bins into bigger bin
        too_small = (9,5), (11,0), (13,0), (15,5)
        for folc_bin, last in too_small:
            for k in input_keys:
                patch = getattr(self,k)[folc_bin]
                summed = sum(patch[last:])
                for i in range(last,len(patch)):
                    patch[i] = summed

        #calculate inner
        self.inner = numpy.true_divide(self.inner, self.total)

        bins = self.bins
        step_size = bins[2]/bins[1]
        centers = numpy.sqrt(bins[1:]*bins[:-1])
        for i,bucket in enumerate(self.power):
            for j,row in enumerate(bucket):
                if not self.total[i,j]:
                    continue
                #scale for distance and the width of the bucket
                scale = step_size/(step_size-1)/self.total[i,j]
                line = row/bins[1:] * scale
                a,b = numpy.polyfit(numpy.log(centers),numpy.log(line),1)
                self.a[i,j] = a
                self.b[i,j] = b

        self.rand = numpy.maximum(0,1-self.inner+(math.e**self.b)/(self.a+1))
        result = self.to_d('a', 'b', 'inner', 'rand')
        write_json([result], "params")

    def to_d(self, *keys):
        return dict((k,getattr(self,k).tolist()) for k in keys)
