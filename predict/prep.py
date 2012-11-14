import random
import bisect
import itertools
import collections
from itertools import chain

import numpy as np

from base import utils, gob
from base.models import User, Tweets, Edges


NEBR_FLAGS = {
    'fols':4,
    'frds':2,
    'ated':1,
}


@gob.mapper(all_items=True)
def pred_users(uids):
    for g in utils.grouper(100,uids,dontfill=True):
        ids_group = tuple(g)
        for u in User.find(User._id.is_in(ids_group)):
            yield u.to_d()


MlocBlur = collections.namedtuple('MlocBlur',('omit','buckets','ratios'))


def _prep_nebr(nebr,contacts):
    # FIXME: these flags are really ugly.
    kind = sum(
            bit if nebr._id in contacts[key] else 0
            for key,bit in NEBR_FLAGS.iteritems()
            )
    return dict(
        folc=nebr.friends_count,
        frdc=nebr.followers_count,
        lofrd=nebr.local_friends,
        lofol=nebr.local_followers,
        lat=nebr.geonames_place.lat,
        lng=nebr.geonames_place.lng,
        mdist=nebr.geonames_place.mdist,
        kind=kind,
        prot=nebr.protected,
        _id=nebr._id,
        )


def _blur_gnp(mb, user_d):
    gnp = user_d.get('gnp')
    if not gnp or gnp['mdist']>1000:
        return None
    if random.random()>mb.omit:
        return None
    index = bisect.bisect(mb.buckets,gnp['mdist'])
    ratio = mb.ratios[index]
    # exaggerate the error that is already there according to the ratio
    for key,real in zip(('lng','lat'),user_d['mloc']):
        delta = real-gnp[key]
        gnp[key] = real+ratio*delta
    gnp['mdist'] = ratio*gnp['mdist']
    return gnp


@gob.mapper(slurp={'mloc_blur':tuple})
def nebrs_d(user_d,mloc_blur):
    mb = MlocBlur(*mloc_blur)

    nebrs = User.find(User._id.is_in(user_d['nebrs']))
    tweets = Tweets.get_id(user_d['_id'],fields=['ats'])
    rfrds = set(user_d['rfrds'])

    contacts = dict(
        ated = set(tweets.ats or []),
        frds = rfrds.union(user_d['jfrds']),
        fols = rfrds.union(user_d['jfols']),
    )

    res = dict(
        _id = user_d['_id'],
        mloc = user_d['mloc'],
        nebrs = [_prep_nebr(nebr,contacts) for nebr in nebrs],
        gnp = _blur_gnp(mb, user_d),
        )
    if 'utco' in user_d:
        res['utco'] = user_d['utco']
    yield res


@gob.mapper()
def mloc_blur(env):
    cutoff = 250000
    mdists = {}
    for key in ('mloc','contact'):
        # FIXME: remove calls to env, use slurp instead
        files = env.split_files(key+'_mdist')
        items_ = chain.from_iterable(env.load(f,'mp') for f in files)
        mdists[key] = filter(None,itertools.islice(items_,cutoff))
    yield 1.0*len(mdists['contact'])/len(mdists['mloc'])

    count = len(mdists['contact'])
    step = count//100
    mdists['mloc'] = mdists['mloc'][:count]
    for key,items in mdists.iteritems():
        mdists[key] = sorted(items)
    # the boundaries of the 100 buckets
    yield mdists['mloc'][step:step*100:step]

    ml_pts = np.array(mdists['mloc'][step/2::step])
    ct_pts = np.array(mdists['contact'][step/2::step])
    # the ratio at the middle of the buckets
    yield list(ct_pts/ml_pts)


@gob.mapper(all_items=True)
def utc_offset(nebrs_d):
    lngs = []
    utcos = []
    for u in nebrs_d:
        if 'utco' in u:
            utcos.append(u['utco'])
            lngs.append(u['mloc'][0])

    offsets = lngs-np.array(utcos)/240
    wrapped = np.mod(offsets+180,360)-180

    counts,bins = np.histogram(wrapped,range(-180,181,15))
    yield list(1.0*counts/sum(counts))


@gob.mapper(all_items=True)
def mdist_real(nebrs_d):
    data = collections.defaultdict(list)
    for nebr_d in nebrs_d:
        if not nebr_d['gnp']:
            continue
        data['glat'].append(nebr_d['gnp']['lat'])
        data['glng'].append(nebr_d['gnp']['lng'])
        data['mlng'].append(nebr_d['mloc'][0])
        data['mlat'].append(nebr_d['mloc'][1])
        data['mdist'].append(nebr_d['gnp']['mdist'])

    dists = utils.np_haversine(
                data['mlng'], data['glng'],
                data['mlat'], data['glat'])
    return itertools.izip(data['mdist'],dists)


@gob.mapper(all_items=True)
def mdist_curves(mdist_real):
    CHUNKS = 10
    dists_ = np.array(list(mdist_real))
    dists = dists_[dists_[:,0].argsort()]

    dist_count = dists.shape[0]
    # cut off the start to make even chunks
    chunks = np.split(dists[(dist_count%CHUNKS):,:],CHUNKS)
    bins = utils.dist_bins(30)

    for index,chunk in enumerate(chunks):
        row = chunk[:,1]
        hist,b = np.histogram(row,bins)

        bin_mids = (b[:-1]+b[1:])/2
        bin_areas = np.pi*(b[1:]**2 - b[:-1]**2)
        scaled_hist = hist/(bin_areas*len(row))
        window = np.bartlett(5)
        smooth_hist=np.convolve(scaled_hist,window,mode='same')/sum(window)
        coeffs = np.polyfit(
                    np.log(bin_mids[1:121]),
                    np.log(smooth_hist[1:121]),
                    3)

        yield dict(
                coeffs = list(coeffs),
                cutoff = 0 if index==0 else chunk[0,0],
                local = scaled_hist[0],
                )


