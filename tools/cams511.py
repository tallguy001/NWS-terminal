#!/usr/bin/env python3
"""
Road-camera inventory for the states whose cameras are listed only by their 511 website (v3.87.0).

Camera locations and ids change slowly, and each site's snapshot address always serves that camera's newest picture, so
the app does not ask these sites for their lists live. This script reads each list once, slowly (one request every two
seconds per site), and writes geo/cams511/<st>.json plus geo/cams511/index.json. The app reads those files and loads
the pictures straight from the agencies.

Two kinds of site, both read the way the site's own map reads them, with no key, no login, no faked header:
  - the older Castle Rock 511 sites: GET /List/GetData/Cameras, a paged list, 100 cameras a page;
  - the newer ones: POST /api/graphql with the site's own two queries (its map's camera layer for the places, its camera
    list for the views). These servers answer only the exact query text their website sends, so the text is kept as sent.
Video is kept only where the site says no sign-in is needed, the stream is HLS and the address carries no token.

Run from the repository root:  python3 tools/cams511.py            (every state)
                               python3 tools/cams511.py GA FL      (just these)
"""
import json, os, sys, time, urllib.parse, urllib.request

UA = 'NWS-Terminal camera inventory (personal weather app; a few requests a day)'
OUT = os.path.join('geo', 'cams511')
PAUSE = 2.0

LIST_SITES = {   # state code: (host, credit, keep only rows whose own state column names this state)
    'fl': ('fl511.com', 'FL511 (Florida DOT)', None), 'ga': ('511ga.org', '511GA (Georgia DOT)', None), 'ut': ('udottraffic.utah.gov', 'UDOT Traffic', None),
    'pa': ('www.511pa.com', '511PA (PennDOT)', None), 'nc': ('www.drivenc.gov', 'DriveNC (NCDOT)', None), 'nv': ('www.nvroads.com', 'NVRoads (Nevada DOT)', None),
    'az': ('az511.com', 'AZ511 (ADOT)', None), 'id': ('511.idaho.gov', 'Idaho 511 (ITD)', None), 'ct': ('ctroads.org', 'CTroads (CTDOT)', None),
    'la': ('511la.org', '511LA (DOTD)', None), 'ak': ('511.alaska.gov', 'Alaska 511 (DOT&PF)', None),
    'me': ('newengland511.org', 'New England 511 (MaineDOT)', 'Maine'), 'nh': ('newengland511.org', 'New England 511 (NHDOT)', 'New Hampshire'), 'vt': ('newengland511.org', 'New England 511 (VTrans)', 'Vermont'),
}
GQL_SITES = {
    'ne': ('www.511.nebraska.gov', 'Nebraska 511 (NDOT)'), 'in': ('511in.org', 'TrafficWise 511 (INDOT)'),
    'ks': ('www.kandrive.gov', 'KanDrive (KDOT)'), 'ma': ('mass511.com', 'Mass511 (MassDOT)'),
}
# The sites' own query text, as their pages send it. Do not reformat.
GQL_LIST = ('query ($input: ListArgs!) { listCameraViewsQuery(input: $input) { cameraViews { category icon '
            'lastUpdated { timestamp timezone } title uri url sources { type src } parentCollection { title uri '
            'icon color location { routeDesignator } lastUpdated { timestamp timezone } } } totalRecords error '
            '{ message type } } }')
GQL_MAP = ('query MapFeatures($input: MapFeaturesArgs!, $plowType: String) { mapFeaturesQuery(input: $input) { '
           'mapFeatures { bbox title tooltip uri features { id geometry properties type } ... on Cluster { maxZoom } '
           '... on Sign { signDisplayType } ... on Event { priority } __typename ... on Camera { active views(limit: '
           '5) { uri ... on CameraView { url } category } } ... on Plow { views(limit: 5, plowType: $plowType) { uri '
           '... on PlowCameraView { url } category } } } error { message type } } }')


def get(url, body=None, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={'User-Agent': UA, 'Accept': 'application/json', **({'Content-Type': 'application/json'} if body else {})})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:   # a busy site answers an HTML page or times out: wait longer and ask again
            if i == tries - 1:
                raise RuntimeError(f'{url[:80]}: {e}')
            time.sleep(PAUSE * 3 * (i + 1))


def video_ok(u, auth):
    u = u or ''
    return u if (not auth and u.startswith('https://') and '.m3u8' in u and 'token=' not in u) else ''


def clip(s, n):
    return ' '.join(str(s or '').split())[:n]


def read_rows(host):
    rows, start, total = [], 0, None
    while total is None or start < total:
        q = {'draw': 1, 'columns': [{'data': str(i), 'name': '', 'searchable': True, 'orderable': True, 'search': {'value': '', 'regex': False}} for i in range(8)],
             'order': [{'column': 0, 'dir': 'asc'}], 'start': start, 'length': 100, 'search': {'value': '', 'regex': False}}
        j = get(f'https://{host}/List/GetData/Cameras?query=' + urllib.parse.quote(json.dumps(q)) + '&lang=en-US')
        total = j.get('recordsTotal') or 0
        page = j.get('data') or []
        rows += page
        start += 100
        if not page:
            break
        time.sleep(PAUSE)
    return rows


def shape_rows(rows, host, only):
    out = []
    for r in rows:
        if only and (r.get('state') or '') != only:
            continue
        try:
            wkt = r['latLng']['geography']['wellKnownText']
            lon, lat = [float(x) for x in wkt[wkt.index('(') + 1:wkt.index(')')].split()]
        except Exception:
            continue
        if not (17 < lat < 72 and -180 < lon < -60):   # a few rows carry a swapped or zero coordinate
            continue
        place = clip(r.get('location'), 120)
        road = clip(r.get('roadway'), 40)
        d = clip(r.get('direction'), 20)
        d = '' if d.lower() in ('', 'unknown', 'none', 'both directions', 'all directions') else d
        views = [v for v in (r.get('images') or []) if not v.get('disabled') and not v.get('blocked') and v.get('imageUrl')]
        for v in views:
            desc = clip(v.get('description'), 70)
            title = place + (' · ' + desc if desc and desc.lower() not in ('n/a', place.lower()) and len(views) > 1 else '')
            img = v['imageUrl'] if v['imageUrl'].startswith('http') else f'https://{host}{v["imageUrl"]}'
            out.append([str(v.get('id')), round(lat, 5), round(lon, 5), title, '' if road.lower() == 'unknown' else road, d, img,
                        video_ok(v.get('videoUrl'), v.get('isVideoAuthRequired'))])
    return out


def read_gql_site(host):
    gql = lambda query, var: get(f'https://{host}/api/graphql', json.dumps({'query': query, 'variables': var}).encode())
    m = gql(GQL_MAP, {'input': {'north': 85, 'south': -85, 'east': 180, 'west': -180, 'zoom': 14, 'layerSlugs': ['normalCameras'], 'nonClusterableUris': ['dashboard']}, 'plowType': 'plowCameras'})
    where = {}
    for f in (m.get('data') or {}).get('mapFeaturesQuery', {}).get('mapFeatures') or []:
        if f.get('__typename') == 'Camera' and f.get('bbox'):
            where[f['uri']] = (f['bbox'][0], f['bbox'][1])
    time.sleep(PAUSE)
    views, off = [], 0
    while True:
        j = gql(GQL_LIST, {'input': {'west': -180, 'south': -85, 'east': 180, 'north': 85, 'sortDirection': 'DESC', 'sortType': 'ROADWAY', 'freeSearchTerm': '',
                                      'classificationsOrSlugs': [], 'recordLimit': 250, 'recordOffset': off}})
        q = (j.get('data') or {}).get('listCameraViewsQuery') or {}
        page = q.get('cameraViews') or []
        views += page
        off += 250
        if len(page) < 250 or off >= (q.get('totalRecords') or 0):
            break
        time.sleep(PAUSE)
    out = []
    for v in views:
        pc = v.get('parentCollection') or {}
        at = where.get(pc.get('uri')) or where.get(v.get('uri'))
        url = v.get('url') or ''
        if not at or not url.startswith('https://') or not (17 < at[1] < 72 and -180 < at[0] < -60):
            continue   # a camera that is down gets an icon path as its picture
        vid = ''
        for s in v.get('sources') or []:
            if (s.get('type') == 'application/x-mpegURL' or (s.get('src') or '').endswith('.m3u8')):
                vid = video_ok(s.get('src'), False)
                break
        road = clip(((pc.get('location') or {}).get('routeDesignator')), 40)
        out.append([v.get('uri', '').split('/')[-1] or str(len(out)), round(at[1], 5), round(at[0], 5), clip(v.get('title') or pc.get('title'), 140), road, '', url, vid])
    return out


def main():
    want = [a.lower() for a in sys.argv[1:]] or list(LIST_SITES) + list(GQL_SITES)
    os.makedirs(OUT, exist_ok=True)
    ipath = os.path.join(OUT, 'index.json')
    index = json.load(open(ipath)) if os.path.exists(ipath) else {}
    cache = {}
    for st in want:
        try:
            if st in LIST_SITES:
                host, credit, only = LIST_SITES[st]
                if host not in cache:   # New England serves three states from one list: read it once, split it by each row's own state
                    cache[host] = read_rows(host)
                rows = shape_rows(cache[host], host, only)
            elif st in GQL_SITES:
                host, credit = GQL_SITES[st]
                rows = read_gql_site(host)
            else:
                print('unknown state', st)
                continue
        except Exception as e:
            print(st, 'FAILED, kept the last file:', e)
            continue
        if not rows:
            print(st, 'no cameras came back, kept the last file')
            continue
        old = index.get(st, {}).get('count', 0)
        if old and len(rows) < old * 0.6:
            print(st, f'only {len(rows)} of {old} cameras came back, kept the last file')
            continue
        lats, lons = [r[1] for r in rows], [r[2] for r in rows]
        with open(os.path.join(OUT, st + '.json'), 'w') as f:
            json.dump({'st': st, 'credit': credit, 'host': host, 'at': int(time.time()), 'fields': ['id', 'lat', 'lon', 'title', 'road', 'dir', 'img', 'video'], 'cams': rows}, f, separators=(',', ':'))
        index[st] = {'credit': credit, 'count': len(rows), 'box': [round(min(lons) - 0.2, 2), round(min(lats) - 0.2, 2), round(max(lons) + 0.2, 2), round(max(lats) + 0.2, 2)], 'at': int(time.time())}
        print(st, len(rows), 'cameras', index[st]['box'])
        time.sleep(PAUSE)
    with open(ipath, 'w') as f:
        json.dump(index, f, separators=(',', ':'), sort_keys=True)


if __name__ == '__main__':
    main()
