OUTPUT_TYPE = 'pdf'#, 'pdf', or None
OUTPUT_TYPE = 'png'
#OUTPUT_TYPE = None

import random
import contextlib
import math
from collections import defaultdict
from operator import itemgetter

import matplotlib

# this needs to happen before pyplot is imported - it cannot be changed
if OUTPUT_TYPE:
    matplotlib.use('Agg')

import matplotlib.pyplot as plt
import PIL
import numpy as np

from friendloc.explore import peek
from friendloc.base.utils import dist_bins, coord_in_miles
from friendloc.base import gob, utils


#CONTACT_GROUPS = dict(
#    jfol = ('just followers','b','dashed',2),
#    jfrd = ('just friends','b','dotted',2),
#    rfrd = ('recip friends','b','solid',1),
#    jat = ('just mentioned','b','dashdot',2),
#)
FL_BLUE = '#1875d5'
FL_GREEN = '#1cf437'
FL_PURP = '#c71fe2'
CONTACT_GROUPS = dict(
    jfol = ('just followers',FL_PURP,'solid',2),
    jfrd = ('just friends',FL_BLUE,'solid',2),
    rfrd = ('recip friends','k','solid',2),
    jat = ('just mentioned',FL_GREEN,'solid',2),
)


@contextlib.contextmanager
def axes(path='', figsize=(12,8), legend_loc=4,
         xlabel=None, ylabel=None, xlim=None, ylim=None, ):
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(111)
    yield ax
    if xlim is not None:
        try:
            ax.set_xlim(*xlim)
        except TypeError:
            ax.set_xlim(0,xlim)
    if ylim is not None:
        try:
            ax.set_ylim(*ylim)
        except TypeError:
            ax.set_ylim(0,ylim)

    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    if legend_loc:
        ax.legend(loc=legend_loc)
    if OUTPUT_TYPE:
        fig.tight_layout()
        fig.savefig('../www/'+path+'.'+OUTPUT_TYPE,bbox_inches='tight')


def linhist(ax, row, bins, dist_scale=False, window=None, normed=False,
            marker='-', **hargs):
    "works like ax.hist, but without jagged edges"
    hist,b = np.histogram(row,bins)
    step_size = b[2]/b[1]
    hist = hist*(1.0*step_size/(step_size-1))
    if window is not None:
        hist = np.convolve(hist,window,mode='same')/sum(window)
    if normed:
        hist = hist * (1.0/len(row))
    if dist_scale:
        hist = hist/b[1:]
        ax.set_yscale('log')
    ax.set_xscale('log')
    ax.plot((b[:-1]+b[1:])/2, hist, marker, **hargs)

def ugly_graph_hist(data,path,kind="sum",figsize=(12,8),legend_loc=None,normed=False,
        sample=None, histtype='step', marker='-', logline_fn=None,
        label_len=False, auto_ls=False, ax=None,
        window=None, ordered_label=False, key_order=None, **kwargs):
    # DEPRECATED - TOO COMPLEX!
    if ax:
        fig = None
    else:
        fig = plt.figure(figsize=figsize)
        ax = fig.add_subplot(111)

    if not isinstance(data,dict):
        data = {"":data}

    hargs = {}
    if kind == 'power':
        ax.set_xscale('log')
        ax.set_yscale('log')
        hargs['log']=True
    elif kind == 'linear':
        pass
    elif kind == 'logsquare':
        ax.set_xscale('log')
    elif kind == 'logline':
        ax.set_xscale('log')
        if legend_loc is None:
            legend_loc = 9
    elif kind == 'cumulog':
        ax.set_xscale('log')
        hargs['cumulative']=True
        if legend_loc is None:
            legend_loc = 4
    else:
        hargs['cumulative']=True
        if legend_loc is None:
            legend_loc = 4

    for known in ['bins']:
        if known in kwargs:
            hargs[known] = kwargs[known]

    if key_order is None:
        key_order = sorted(data.iterkeys())

    for index,key in enumerate(key_order):
        if isinstance(key,basestring):
            hargs['label'] = key
        else:
            for k,v in zip(['label','color','linestyle','linewidth'],key):
                if v is not None:
                    hargs[k] = v
        if ordered_label:
            hargs['label'] = hargs['label'][2:]

        if auto_ls:
            hargs['linestyle'] = ('solid','dashed','dashdot','dotted')[index/7]

        row = data[key]
        if sample:
            row = random.sample(row,sample)
        if normed:
            weight = 1.0/len(row)
            hargs['weights'] = [weight]*len(row)
        if label_len:
            hargs['label'] = "%s (%d)"%(hargs['label'],len(row))

        if kind=="logline":
            for k in ['weights','log','bins']:
                if k in hargs:
                    del hargs[k]
            hist,b = np.histogram(row,kwargs['bins'])
            step_size = b[2]/b[1]
            hist = hist*(1.0*step_size/(step_size-1))
            if window is not None:
                hist = np.convolve(hist,window,mode='same')/sum(window)
            if normed:
                hist = hist*weight
            if logline_fn:
                logline_fn(ax, row, b, hist)
            ax.plot((b[:-1]+b[1:])/2, hist, marker, **hargs)
        else:
            ax.hist(row, histtype=histtype, **hargs)
    if normed and kind!='logline':
        ax.set_ylim(0,1)
    elif 'ylim' in kwargs:
        try:
            ax.set_ylim(*kwargs['ylim'])
        except TypeError:
            ax.set_ylim(0,kwargs['ylim'])
    if 'xlim' in kwargs:
        try:
            ax.set_xlim(*kwargs['xlim'])
        except TypeError:
            ax.set_xlim(0,kwargs['xlim'])
    if legend_loc:
        ax.legend(loc=legend_loc)
    ax.set_xlabel(kwargs.get('xlabel'))
    ax.set_ylabel(kwargs.get('ylabel'))
    if fig is not None:
        fig.tight_layout()
        fig.savefig('../www/'+path,bbox_inches='tight')



@gob.mapper(all_items=True)
def graph_vect_fit(vect_fit, in_paths, env):
    """ graph four example pContact curves and all the curves of best fit """
    if in_paths[0][-1] != '0':
        return
    ratios = (ratio
              for vers,cutoff,ratio in env.load('vect_ratios.0')
              if vers=='leaf')
    fits = (fit for vers,cutoff,fit in vect_fit if vers=='leaf')

    bins = dist_bins(120)
    miles = np.sqrt([bins[x-1]*bins[x] for x in xrange(2,482)])

    with axes('vect_fit',legend_loc=1) as ax:
        ax.set_xlim(1,10000)
        ax.set_ylim(1e-8,1e-3)
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel('distance in miles')
        ax.set_ylabel('probability of being a contact')

        colors = iter([FL_PURP,FL_BLUE,FL_GREEN,'k'])
        labels = iter([
            'edges predicted in nearest 10%',
            'edges in 60th to 70th percentile',
            'edges in 30th to 40th percentile',
            'edges predicted in most distant 10%',
        ])
        for index,(ratio,fit) in enumerate(zip(ratios, fits)):
            if index%3==0:
                color = next(colors)
                label = next(labels)
                fitstyle='dashed'
            else:
                color = ".6"
                label = None
                fitstyle='dotted'
            window = np.bartlett(5)
            smooth_ratio = np.convolve(ratio,window,mode='same')/sum(window)
            if label:
                ax.plot(miles, smooth_ratio, '-', color=color, label=label,
                        linewidth=2)
            ax.plot(miles, peek.contact_curve(miles,*fit), '-',
                    linewidth=2,
                    linestyle=fitstyle,
                    color=color,
                   )


@gob.mapper(all_items=True)
def graph_stranger_mat(stranger_mat):
    """
    create an image from pStranger---the probability that a user lives at a
    place based on the contacts the user is not connected to
    """
    mat = np.transpose(next(stranger_mat))
    scaled = 1.1**mat
    fit = 255.999*(scaled-np.min(scaled))/np.ptp(scaled)
    buff = np.require(fit,np.uint8,['C_CONTIGUOUS'])
    img = PIL.Image.frombuffer('L',(3600,1800),buff)
    img.save('stranger_mat.png')


@gob.mapper(all_items=True)
def graph_example_probs(vect_fit, in_paths):
    """
    create an example of maximum likeliehood estimation for four friends
    """
    if in_paths[0][-1] != '0':
        return
    curves = [fit for vers,cutoff,fit in vect_fit if vers=='leaf']

    lat_range = np.linspace(27.01,32.99,5*60)
    lng_range = np.linspace(-100.99,-93.01,5*80)
    lat_grid, lng_grid = np.meshgrid(lat_range, lng_range)
    print lat_range, lng_range

    probs = np.zeros_like(lat_grid)

    spots = (
        (-95.31, 29.73, 0), # Houston
        (-96.37, 30.67, 1), # Bryan, TX
        (-99.25, 31.25, 5), # Texas
        (-97.74, 30.27, 3), # Austin
    )
    for lng, lat, curve in spots:
        dists = utils.np_haversine(lng, lng_grid, lat, lat_grid)
        probs+=np.log(peek.contact_curve(dists,*(curves[curve])))

    clipped = 255.999*(np.max(probs)-probs)/np.ptp(probs)
    buff = np.require(np.transpose(clipped),np.uint8,['C_CONTIGUOUS'])
    img = PIL.Image.frombuffer('L',(clipped.shape),buff)
    img.save('example_probs.png')


@gob.mapper(all_items=True)
def gr_basic(preds):
    """graph for evaluation"""
    labels = dict(
        backstrom=("Backstrom Baseline",FL_GREEN,'solid',2),
        #last="Random Contact",
        #median="Median Contact",
        #mode="Mode of Contacts",
        nearest=("Nearest Predicted Contact",FL_PURP,'solid',2),
        friendloc_basic=("FriendlyLocation Basic",FL_BLUE,'solid',2),
        friendloc_cut=("FriendlyLocation+Cutoff",'k','solid',2),
        #omni="Omniscient",
    )
    _gr_preds(preds,labels,'fl_basic.png')


@gob.mapper(all_items=True)
def gr_parts(preds):
    """graph for all the evaluations"""
    labels = dict(
        backstrom="Backstrom Baseline",
        friendloc_plain="FriendlyLocation Basic",
        friendloc_cut0="FriendlyLocation with Cutoff",
        friendloc_cut="FriendlyLocation with Cutoff +loc +str",
        friendloc_strange="FriendlyLocation with Strange",
        friendloc_tz="FriendlyLocation with UTC offset",
        friendloc_loc="FriendlyLocation with Location field",
        friendloc_full="FriendlyLocation Full",
        omni="Omniscient Baseline",
    )
    _gr_preds(preds,labels,'fl_parts.pdf')

def _aed(ratio,vals):
    return np.average(sorted(vals)[:int(ratio*len(vals))])

def _gr_preds(preds,labels,path):
    preds_d = defaultdict(list)
    for key,dists in preds:
        preds_d[key].extend(dists)
    data = {labels[key]:preds_d[key] for key in labels}

    ugly_graph_hist(data,
            path,
            xlim= (1,15000),
            normed=True,
            label_len=True,
            kind="cumulog",
            #figsize=(12,6),
            ylabel = "fraction of target users",
            xlabel = "error in prediction (miles)",
            bins = dist_bins(120),
            )


@gob.mapper(all_items=True)
def graph_edge_types_cuml(edge_dists):
    """
    graph CDF of distance from target user to contact split by contact type
    """
    data = defaultdict(list)

    for key,dists in edge_dists:
        if key[0]=='usa':
            continue
        conf = CONTACT_GROUPS[key[0]]
        data[conf].extend(dists)

    for k,v in data.iteritems():
        print k,sum(1.0 for x in v if x<25)/len(v)

    ugly_graph_hist(data,
            "edge_types_cuml.png",
            xlim= (1,15000),
            normed=True,
            label_len=True,
            kind="cumulog",
            #figsize=(12,6),
            ylabel = "fraction of edges",
            xlabel = "length of edge in miles",
            bins = dist_bins(120),
            )

@gob.mapper(all_items=True)
def graph_edge_types_prot(edge_dists):
    """ graph CDF of distance to protected vs public accounts """
    data = defaultdict(list)

    for key,dists in edge_dists:
        if key[0]=='usa':
            continue
        conf = CONTACT_GROUPS[key[0]]
        fill = 'solid' if key[-1] else 'dotted'
        label,color,oldfill,width = conf
        data[(label,color,fill)].extend(dists)

    for k,v in data.iteritems():
        print k,round(100*sum(1.0 for x in v if x<25)/len(v)),len(v)

    ugly_graph_hist(data,
            "edge_types_prot.pdf",
            xlim = (1,15000),
            normed=True,
            label_len=True,
            kind="cumulog",
            ylabel = "fraction of users",
            xlabel = "length of edge in miles",
            bins = dist_bins(80),
            )

@gob.mapper(all_items=True)
def graph_rfrd_norm(edge_dists):
    """ graph of distribution of distance to recip friends """
    data = defaultdict(list)
    for key,dists in edge_dists:
        if key[0]!='rfrd':
            continue
        data[key[0]].extend(dists)

    ugly_graph_hist({"recip friends":data['rfrd']},
        'rfrd_norm.pdf',
        bins=dist_bins(40),
        xlim=(1,15000),
        ylim=(0,3100),
        figsize=(12,4),
        label_len=True,
        legend_loc=2,
        kind="logsquare",
        xlabel = "length of edge in miles",
        ylabel = "number of users",
        )


@gob.mapper(all_items=True)
def graph_edge_types_norm(edge_dists):
    """ graph of distribution of distance to four types of friends """
    data = defaultdict(list)
    for key,dists in edge_dists:
        if key[0]=='usa':
            continue
        data[key[0]].extend(dists)
    smallest = min(len(v) for v in data.itervalues())

    fig = plt.figure(figsize=(12,12))
    for spot,key in enumerate(['rfrd','jfol','jfrd','jat']):
        ax = fig.add_subplot(4,1,1+spot)
        xlabel = "distance between edges in miles" if spot==3 else ''
        label = CONTACT_GROUPS[key][0]
        ugly_graph_hist({label:random.sample(data[key],smallest)},
            'ignored',
            ax=ax,
            bins=dist_bins(40),
            xlim=(1,15000),
            ylim=(0,4000),
            label_len=True,
            legend_loc=2,
            kind="linear",
            xlabel = xlabel,
            ylabel = "number of users",
            )
        ax.set_xscale('log')
        if spot!=3:
            ax.get_xaxis().set_ticklabels([])
    fig.tight_layout()
    fig.savefig("../www/edge_types_norm.pdf",bbox_inches='tight')


@gob.mapper(all_items=True)
def graph_edge_count(rfr_dists):
    """
    graph CDF of distance to recip friends split into bins based on number
    of friends or followers
    """
    frd_data = defaultdict(list)
    fol_data = defaultdict(list)
    labels = ["",'1-9','10-99','100-999','1000-9999','10000+']
    key_labels = dict(frdc='Friends',folc='Followers')

    for amigo in rfr_dists:
        for color,key,data in ((FL_PURP,'folc',fol_data),(FL_BLUE,'frdc',frd_data)):
            bin = min(5,len(str(int(amigo[key]))))
            label = '%s %s'%(labels[bin],key_labels[key])
            # 1.6**(bin-1) is the line width calculation
            data[label,color,'solid',1.6**(bin-2)].append(amigo['dist'])

    fig = plt.figure(figsize=(18,9))
    for spot,data in enumerate((fol_data,frd_data)):
        ax = fig.add_subplot(1,2,1+spot)
        ugly_graph_hist(data,
            'ignored',
            ax=ax,
            bins=dist_bins(120),
            xlim=(1,15000),
            label_len=True,
            legend_loc=2,
            kind="cumulog",
            normed=True,
            xlabel = "length of edge in miles",
            ylabel = "fraction of edges",
            )
    fig.tight_layout()
    fig.savefig("../www/edge_counts.png",bbox_inches='tight')


@gob.mapper(all_items=True)
def graph_locals_10(rfr_dists):
    """
    graph comparison of recip friends split into bins based on the friend's
    local contact ratio. (LCR is based on only 10 leafs here.)
    """
    labels = [
        (".0<=lcr<.25",FL_BLUE),
        (".25<=lcr<.5",FL_GREEN),
        (".5<=lcr<.75",FL_PURP),
        (".75<=lcr<=1",'k'),
    ]
    data = defaultdict(list)

    for amigo in rfr_dists:
        if amigo['dirt'] is None:
            data[('No leafs','.5','dashed',2)].append(amigo['dist'])
        else:
            label = labels[min(3,int(math.floor(amigo['dirt']*4)))]
            data[label].append(amigo['dist'])
        #if amigo['dirt']==.25:
        #    data['lcr==.25','.5','dashed'].append(amigo['dist'])

    ugly_graph_hist(data,
        'locals_10.png',
        bins=dist_bins(120),
        xlim=(1,15000),
        label_len=True,
        kind="cumulog",
        normed=True,
        figsize=(12,6),
        xlabel = "length of edge in miles",
        ylabel = "fraction of edges",
        )


@gob.mapper(all_items=True)
def graph_locals_cmp(rfr_dists):
    """
    graph to determine optimal number of leafs to include in local contact
    ratio calculation. LCR is calculated for 10, 20, and 100 leafs. We plot the
    distances to contacts who have a better-than-median LCR.
    """
    ratio_dists = defaultdict(list)
    for amigo in rfr_dists:
        for key in ('dirt','aint','cheap'):
            if amigo[key] is not None:
                ratio_dists[key].append((amigo[key],amigo['dist']))

    keys = ['dirt','cheap','aint']
    labels = [
        ('10 leafs','b','dashed',2),
        ('20 leafs','r','dotted',2),
        ('100 leafs','k','solid',1),
    ]

    good_dists = {}
    for key,label in zip(keys,labels):
        tups = ratio_dists[key]
        med = np.median([ratio for ratio,dist in tups])
        good_dists[label] = [dist for ratio,dist in tups if ratio>=med]

    for k,v in good_dists.iteritems():
        print k,sum(1.0 for x in v if x<25)/len(v)

    ugly_graph_hist(good_dists,
        'locals_cmp.pdf',
        bins=dist_bins(120),
        xlim=(1,15000),
        figsize=(12,6),
        label_len=True,
        kind="cumulog",
        normed=True,
        xlabel = "length of edge in miles",
        ylabel = "fraction of edges",
        key_order = labels,
        )


@gob.mapper(all_items=True)
def graph_com_types(edge_dists):
    """
    graph of distance to contacts split based on communication patterns
    """
    data = defaultdict(lambda: defaultdict(list))

    for key,dists in edge_dists:
        if key[0]=='usa':
            continue
        edge_type,i_at,u_at,prot = key
        # ignore protected
        data[edge_type][i_at,u_at].extend(dists)


    titles = dict(
        jfol="Just Follower",
        rfrd="Reciprical Friend",
        jfrd="Just Friend",
        jat="Just Mentiened")
    labels = {
        (False,False):"We ignore",
        (True,False):"I talk",
        (False,True):"You talk",
        (True,True):"We talk",
        }
    fig = plt.figure(figsize=(18,12))

    for edge_type,sub_d in data.iteritems():
        for mentions,dists in sub_d.iteritems():
            print edge_type, mentions, 1.0*sum(1 for d in dists if d<25)/len(dists)

    for spot,edge_type in enumerate(['rfrd','jfrd','jfol','jat']):
        ax = fig.add_subplot(2,2,1+spot)

        # UGLY
        picked = {
            labels[key]:dists
            for key,dists in data[edge_type].iteritems()
        }

        ugly_graph_hist(picked, "", ax=ax,
                legend_loc=2,
                bins=dist_bins(80),
                kind="cumulog",
                xlim=(1,15000),
                normed=True,
                label_len=True,
                xlabel = "length of edge in miles",
                ylabel = "number of edges",
                )
        ax.set_title(titles[edge_type])
    fig.tight_layout()
    fig.savefig("../www/com_types.pdf",bbox_inches='tight')


@gob.mapper(all_items=True)
def graph_mloc_mdist(mloc_mdists):
    """
    graph of location error for target users when they are split into bins based
    on their median location error
    """
    dists = defaultdict(list)
    labels = ["",'0-10','10-100','100-1000','1000+']
    for mloc,mdist in mloc_mdists:
            bin = min(4,len(str(int(mdist))))
            width = .6*1.8**(bin-1)
            dists[labels[bin],'b','solid',width].append(mloc)
            dists[('MLE','k','dashed',1)].append(mdist)
    for key,vals in dists.iteritems():
        print key,sum(1 for v in vals if v<1000)

    ugly_graph_hist(dists,
            "mloc_mdist.pdf",
            bins = dist_bins(120),
            kind="cumulog",
            normed=True,
            label_len=True,
            xlim=(1,30000),
            xlabel = "location error in miles",
            ylabel = "fraction of users",
            )


@gob.mapper(all_items=True)
def near_triads(rfr_triads):
    """
    Comparison of distance to mutual friend (labeled our) vs non-mutual friend
    (labeled my).
    """
    labels = ["",'0-10','10-100','100-1000','1000+']
    data = defaultdict(list)

    for quad in rfr_triads:
        for key,color,fill in (('my','b','dashed'),('our','r','solid')):
            edist = coord_in_miles(quad[key]['loc'],quad['you']['loc'])
            bin = min(4,len(str(int(edist))))
            label = '%s %s'%(key,labels[bin])
            dist = coord_in_miles(quad[key]['loc'],quad['me']['loc'])
            width = .6*1.8**(bin-1)
            data[label,color,'solid',width].append(dist)
    ugly_graph_hist(data,
            "near_triads.pdf",
            bins=dist_bins(120),
            xlim=(1,30000),
            label_len=True,
            kind="cumulog",
            normed=True,
            xlabel = "distance between edges in miles",
            ylabel = "number of users",
            )


@gob.mapper(all_items=True)
def graph_rfrd_mdist(edges_d):
    """
    graph CDF of distance to recip friend split into bins based on median
    location error
    """
    data = defaultdict(list)
    labels = ["",'0<=MLE<10','10<=MLE<100','100<=MLE<1000']

    for edge_d in edges_d:
        amigo = edge_d.get('rfrd')
        if not amigo:
            continue
        dist = coord_in_miles(edge_d['mloc'],amigo)
        bin = len(str(int(amigo['mdist'])))
        width = .3*2.5**bin
        data[labels[bin],FL_PURP,'solid',width].append(dist)

    for label, dists in data.iteritems():
        print label,peek.local_ratio(dists),peek.local_ratio(dists,1000),len(dists)

    ugly_graph_hist(data,
            "rfrd_mdist.png",
            xlim= (1,15000),
            normed=True,
            label_len=True,
            kind="cumulog",
            ylabel = "fraction of edges",
            xlabel = "length of edge in miles",
            figsize=(12,6),
            bins = dist_bins(120),
            key_order = sorted(data,key=itemgetter(3)),
            )

@gob.mapper(all_items=True)
def graph_example_contacts():
    """
    Graph the locations of all the contacts of one user. (This is for the
    slides.)
    """
    points = np.array([
            (-104.9847, 39.7392), (-97.7431, 30.2672), (-105.3505, 40.0833),
            (-122.6762, 45.5234), (-97.7431, 30.2672), (-97.6789, 30.5083),
            (-95.3633, 29.7633), (-97.7431, 30.2672), (-97.7431, 30.2672),
            (-96.3344, 30.628), (-97.7431, 30.2672), (-97.0326, 32.763),
            (-87.65, 41.85), (-118.0353, 34.1397), (-122.4194, 37.7749),
            (-97.7431, 30.2672), (-80.0364, 26.7056), (-77.0003, 38.9171),
            (-97.7431, 30.2672), (-76.6497, 39.4668), (-90.4001, 38.6334),
            (-71.1787, 42.3959), (-87.7008, 30.246), (-122.0838, 37.3861),
            (-123.1193, 49.2497), (-122.4203, 37.7767), (-97.7431, 30.2672),
            (-74.006, 40.7143), (-95.2353, 38.9717), (-97.7431, 30.2672),
            (-97.7431, 30.2672), (13.4105, 52.5244), (144.9633, -37.814),
            (-122.0838, 37.3861), (-77.0003, 38.9171), (-73.9133, 40.7577),
            (-122.3321, 47.6062), (-5.9333, 54.5833), (-122.4194, 37.7749),
            (-97.7431, 30.2672), (-73.9524, 40.8854), (-77.0003, 38.9171),
            (-80.0003, 35.5007), (-96.3344, 30.628), (-81.5348, 28.4956),
            (-105.3505, 40.0833), (-75.4999, 43.0004), (-74.006, 40.7143),
            (-75.4999, 43.0004), (-73.9496, 40.6501), (-122.4194, 37.7749),
            (-77.6156, 43.1548), (-122.4194, 37.7749), (-77.0003, 38.9171),
            (-122.4194, 37.7749), (-4.0, 54.0), (-97.7431, 30.2672),
            (5.75, 5.5167), (-4.0, 54.0), (-74.006, 40.7143),
            (-121.9747, 37.2266), (-0.1288, 51.5005), (-77.9819, 35.4971),
            (-97.7431, 30.2672), (-87.8289, 42.1275), (-122.4194, 37.7749),
            (24.7535, 59.437), (-121.7677, 37.2333), (-75.4999, 43.0004),
            (-97.7431, 30.2672), (-122.0838, 37.3861), (26.0, 64.0),
            (-95.3633, 29.7633), (-0.1288, 51.5005), (-104.9847, 39.7392),
            (-121.95, 37.2872), (-122.3763, 37.9191), (-4.0, 54.0),
            (-71.0598, 42.3584), (34.8, 32.0833), (-78.4767, 38.0293),
            (-75.4999, 43.0004), (-71.0609, 42.3535), (-0.1395, 50.8284),
            (12.5655, 55.6759), (-80.0003, 35.5007), (-104.9847, 39.7392),
            (-105.5008, 39.0003), (-0.0918, 51.5128), (34.75, 31.5),
    ])

    with axes('contacts') as ax:
        ax.set_xlim((-126,-66))
        ax.set_ylim((24,50))
        #points+= np.random.normal(0,.1,points.shape)
        ax.plot(points[:,0],points[:,1],'x',
                color='#1cf437',
                markeredgewidth=5,
                markersize=20,
        )
        ax.plot([-97.74],[30.27],'o',
                color='#1875d5',
                markeredgewidth=0,
                markersize=15,
        )
        ax.get_xaxis().set_visible(False)
        ax.get_yaxis().set_visible(False)
        ax.set_frame_on(False)

