""" for handling ui settings """

from typing import List, Dict, Tuple, Callable
import os
from pathlib import Path
from glob import glob
from math import ceil
from re import compile as re_comp, sub as re_sub, match as re_match, IGNORECASE
from json import dumps, loads
from PIL import Image
from modules import shared
from modules.deepbooru import re_special as tag_escape_pattern
from functools import partial

from tagger import format as tags_format

from tagger import settings
Its = settings.InterrogatorSettings

# PIL.Image.registered_extensions() returns only PNG if you call early
supported_extensions = {
    e
    for e, f in Image.registered_extensions().items()
    if f in Image.OPEN
}

# interrogator return type
it_ret_tp = Tuple[
    str,               # tags as string
    Dict[str, float],  # rating confidences
    Dict[str, float],  # tag confidences
    str,               # error message
]


class IOData:
    """ data class for input and output paths """
    last_input_glob = None
    base_dir = None
    output_root = None
    paths = []
    save_tags = True

    @classmethod
    def flip_save_tags(cls) -> callable:
        def toggle():
            cls.save_tags = not cls.save_tags
        return toggle

    @classmethod
    def toggle_save_tags(cls) -> None:
        cls.save_tags = not cls.save_tags

    @classmethod
    def update_output_dir(cls, output_dir: str) -> str:
        """ update output directory, and set input and output paths """
        pout = Path(output_dir)
        if pout != cls.output_root:
            paths = [x[0] for x in cls.paths]
            cls.paths = []
            cls.output_root = pout
            err = cls.set_batch_io(paths)
            return err
        return ''

    @classmethod
    def update_input_glob(cls, input_glob: str) -> str:
        """ update input glob pattern, and set input and output paths """
        input_glob = input_glob.strip()
        if input_glob == cls.last_input_glob:
            print('input glob did not change')
            return ''
        last_input_glob = input_glob

        cls.paths = []

        # if there is no glob pattern, insert it automatically
        if not input_glob.endswith('*'):
            if not input_glob.endswith(os.sep):
                input_glob += os.sep
            input_glob += '*'
        # get root directory of input glob pattern
        base_dir = input_glob.replace('?', '*')
        base_dir = base_dir.split(os.sep + '*').pop(0)
        if not os.path.isdir(base_dir):
            return 'Invalid input directory'

        if cls.output_root is None:
            output_dir = base_dir

            cls.output_root = Path(output_dir)
        elif not cls.output_root or cls.output_root == Path(cls.base_dir):
            cls.output_root = Path(base_dir)

        cls.base_dir_last = Path(base_dir).parts[-1]
        cls.base_dir = base_dir
        err = QData.read_json(cls.output_root)
        if err != '':
            return err

        recursive = getattr(shared.opts, 'tagger_batch_recursive', '')
        paths = glob(input_glob, recursive=recursive)
        print(f'found {len(paths)} image(s)')
        err = cls.set_batch_io(paths)
        if err == '':
            cls.last_input_glob = last_input_glob

        return err

    @classmethod
    def set_batch_io(cls, paths: List[Path]) -> str:
        """ set input and output paths for batch mode """
        checked_dirs = set()
        for path in paths:
            ext = os.path.splitext(path)[1].lower()
            if ext in supported_extensions:
                path = Path(path)
                if not cls.save_tags:
                    cls.paths.append([path, '', ''])
                    continue

                # guess the output path
                base_dir_last_idx = path.parts.index(cls.base_dir_last)
                # format output filename

                info = tags_format.Info(path, 'txt')
                fm = partial(lambda info, m: tags_format.parse(m, info), info)

                try:
                    formatted_output_filename = tags_format.pattern.sub(
                        fm,
                        Its.output_filename_format
                    )
                except (TypeError, ValueError) as error:
                    return f"{path}: output format: {str(error)}"

                output_dir = cls.output_root.joinpath(
                    *path.parts[base_dir_last_idx + 1:]).parent

                tags_out = output_dir.joinpath(formatted_output_filename)

                if output_dir in checked_dirs:
                    cls.paths.append([path, tags_out, ''])
                else:
                    checked_dirs.add(output_dir)
                    if os.path.exists(output_dir):
                        if os.path.isdir(output_dir):
                            cls.paths.append([path, tags_out, ''])
                        else:
                            return f"{output_dir}: not a directory."
                    else:
                        cls.paths.append([path, tags_out, output_dir])
            elif ext != '.txt' and 'db.json' not in path:
                print(f'{path}: not an image extension: "{ext}"')
        return ''


def get_i_wt(stored: float) -> Tuple[int, float]:
    """
    in db.json or InterrogationDB.weighed, with weights + increment in the list
    similar for the "query" dict. Same increment per filestamp-interrogation.
    """
    i = ceil(stored) - 1
    return i, stored - i


class QData:
    """ Query data: contains parameters for the query """
    add_tags = []
    keep_tags = set()
    exclude_tags = set()
    rexcl = None
    search_tags = {}
    replace_tags = []
    re_search = None
    threshold = 0.35
    count_threshold = 100

    json_db = None
    weighed = ({}, {})
    query = {}
    data = None
    ratings = {}
    tags = {}
    inverse = False
    had_renames = False

    @classmethod
    def set(cls, key: str) -> Callable[[str], Tuple[str]]:
        def setter(val) -> Tuple[str]:
            setattr(cls, key, val)
            return ('',)
        return setter

    @classmethod
    def update_keep(cls, keep: str) -> str:
        cls.keep_tags = {x for x in map(str.strip, keep.split(',')) if x != ''}
        return ''

    @classmethod
    def update_add(cls, add: str) -> str:
        cls.add_tags = [x for x in map(str.strip, add.split(',')) if x != '']
        return ''

    @classmethod
    def update_exclude(cls, exclude: str) -> str:
        exclude = exclude.strip()
        # first filter empty strings
        if ',' in exclude:
            filtered = [x for x in map(str.strip, exclude.split(',')) if x != '']
            cls.exclude_tags = set(filtered)
            cls.rexcl = None
        elif exclude != '':
            cls.rexcl = re_comp('^'+exclude+'$', flags=IGNORECASE)
        return ''

    @classmethod
    def update_search(cls, search: str) -> str:
        search = [x for x in map(str.strip, search.split(',')) if x != '']
        cls.search_tags = dict(enumerate(search))
        slen = len(cls.search_tags)
        if len(cls.search_tags) == 1:
            cls.re_search = re_comp('^'+search[0]+'$', flags=IGNORECASE)
        elif slen != len(cls.replace_tags):
            return 'search, replace: unequal len, replacements > 1.'
        return ''

    @classmethod
    def update_replace(cls, replace: str) -> str:
        repl_tag_map = [x for x in map(str.strip, replace.split(',')) if x != '']
        cls.replace_tags = list(repl_tag_map)
        if cls.re_search is None and len(cls.search_tags) != len(cls.replace_tags):
            return 'search, replace: unequal len, replacements > 1.'

    @classmethod
    def read_json(cls, outdir) -> str:
        """ read db.json if it exists """
        cls.json_db = None
        if getattr(shared.opts, 'tagger_auto_serde_json', True):
            cls.json_db = outdir.joinpath('db.json')
            if cls.json_db.is_file():
                cls.had_renames = False
                try:
                    data = loads(cls.json_db.read_text())
                    if any(x not in data for x in ["tag", "rating", "query"]):
                        raise TypeError
                except Exception as err:
                    return f'Error reading {cls.json_db}: {repr(err)}'
                for key in ["add", "keep", "exclude", "search", "replace"]:
                    if key in data:
                        err = getattr(cls, f"update_{key}")(data[key])
                        if err:
                            return err
                cls.weighed = (data["tag"], data["rating"])
                cls.query = data["query"]
                print(f'Read {cls.json_db}: {len(cls.query)} interrogations, {len(cls.tags)} tags.')
        return ''

    @classmethod
    def write_json(cls) -> None:
        """ write db.json """
        if cls.json_db is not None:
            search = sorted(cls.search_tags.items(), key=lambda x: x[0])
            data = {
                "tag": cls.weighed[0],
                "rating": cls.weighed[1],
                "query": cls.query,
                "add": ','.join(cls.add_tags),
                "keep": ','.join(cls.keep_tags),
                "exclude": ','.join(cls.exclude_tags),
                "search": ','.join([x[1] for x in search]),
                "repl": ','.join(cls.replace_tags)
            }
            cls.json_db.write_text(dumps(data, indent=2))
            print(f'Wrote {cls.json_db}: {len(cls.query)} interrogations, {len(cls.tags)} tags.')

    @classmethod
    def get_index(cls, fi_key: str, path='') -> int:
        """ get index for filestamp-interrogator """
        if path and path != cls.query[fi_key][0]:
            if cls.query[fi_key][0] != '':
                print(f'Dup or rename: Identical checksums for {path}\n'
                      f'and: {cls.query[fi_key][0]} (path updated)')
                cls.had_renames = True
            cls.query[fi_key] = (path, cls.query[fi_key][1])

        return cls.query[fi_key][1]

    @classmethod
    def get_single_data(cls, fi_key: str) -> Tuple[Dict[str, float], Dict[str, float]]:
        """ get tags and ratings for filestamp-interrogator """
        index = QData.query.get(fi_key)[1]
        data = [{}, {}]
        for j in range(2):
            for ent, lst in cls.weighed[j].items():
                for i, val in map(get_i_wt, lst):
                    if i == index:
                        data[j][ent] = val

        return tuple(data)


    @classmethod
    def init_query(cls) -> None:
        cls.tags.clear()
        cls.ratings.clear()

    @classmethod
    def is_excluded(cls, ent: str) -> bool:
        """ check if tag is excluded """
        return re_match(cls.rexcl, ent) if cls.rexcl else ent in cls.exclude_tags

    @classmethod
    def apply_filters(
        cls,
        data,
        fi_key: str,
        on_avg: bool,
    ):
        """ apply filters to query data, store in db.json if required """

        replace_underscore = getattr(shared.opts, 'tagger_repl_us', True)

        tags = sorted(data[3].items(), key=lambda x: x[1], reverse=True)
        if cls.inverse:
            # inverse: display all tags marked for exclusion
            for ent, val in tags:
                if replace_underscore and ent not in Its.kamojis:
                    ent = ent.replace('_', ' ')

                if getattr(shared.opts, 'tagger_escape', False):
                    ent = tag_escape_pattern.sub(r'\\\1', ent)

                if cls.re_search:
                    ent = re_sub(cls.re_search, cls.replace_tags[0], ent, 1)
                elif ent in cls.search_tags:
                    ent = cls.replace_tags[cls.search_tags[ent]]

                if ent in cls.keep_tags or ent in cls.add_tags:
                    continue
                if on_avg or cls.is_excluded(ent) or val < cls.threshold:
                    if ent not in cls.tags:
                        cls.tags[ent] = 0.0
                    cls.tags[ent] += val
            return

        # not inverse: display all tags marked for inclusion
        for_tags_file = ""
        do_store = fi_key != ''
        count = 0
        max_ct = QData.count_threshold - len(cls.add_tags)
        ratings = sorted(data[2].items(), key=lambda x: x[1], reverse=True)
        # loop over ratings
        for ent, val in ratings:
            if do_store:
                if ent not in cls.weighed[0]:
                    cls.weighed[0][ent] = []

                cls.weighed[0][ent].append(val + len(cls.query))
            if ent not in cls.ratings:
                cls.ratings[ent] = 0.0

            cls.ratings[ent] += val

        # loop over tags with db update
        for ent, val in tags:
            if isinstance(ent, float):
                print(f'float: {ent} {val}')
                continue
            if do_store:
                if val > 0.005:
                    if ent not in cls.weighed[1]:
                        cls.weighed[1][ent] = []

                    cls.weighed[1][ent].append(val + len(cls.query))

            if count < max_ct:
                if replace_underscore and ent not in Its.kamojis:
                    ent = ent.replace('_', ' ')

                if getattr(shared.opts, 'tagger_escape', False):
                    ent = tag_escape_pattern.sub(r'\\\1', ent)

                if cls.re_search:
                    ent = re_sub(cls.re_search, cls.replace_tags[0], ent, 1)
                elif ent in cls.search_tags:
                    ent = cls.replace_tags[cls.search_tags[ent]]
                if ent not in cls.keep_tags:
                    if cls.is_excluded(ent):
                        continue
                    if not on_avg and val < cls.threshold:
                        continue
                for_tags_file += ", " + ent
                count += 1
            elif not do_store:
                break
            cls.tags[ent] = cls.tags[ent] + val if ent in cls.tags else val

        for tag in cls.add_tags:
            cls.tags[tag] = 1.0

        if getattr(shared.opts, 'tagger_verbose', True):
            print(f'{data[0]}: {count}/{len(tags)} tags kept')

        if do_store:
            cls.query[fi_key] = (data[0], len(cls.query))

        if data[1]:
            data[1].write_text(for_tags_file[2:], encoding='utf-8')

    @classmethod
    def finalize_batch(
        cls,
        in_db,
        ct: int,
        on_avg: bool
    ) -> it_ret_tp:
        """ finalize the batch query """
        if cls.json_db and ct > 0 or cls.had_renames:
            cls.write_json()

        # collect the weights per file/interrogation of the prior in db stored.
        for index in range(2):
            for ent, lst in cls.weighed[index].items():
                for i, val in map(get_i_wt, lst):
                    if i in in_db:
                        in_db[i][2+index][ent] = val

        # process the retrieved from db and add them to the stats
        for got in in_db.values():
            cls.apply_filters(got, '', on_avg)

        # average
        return cls.finalize(ct + len(in_db), on_avg)

    @classmethod
    def finalize(cls, count: int, on_avg: bool) -> it_ret_tp:
        """ finalize the query, return the results """
        tags_str, ratings, tags = '', {}, {}

        def averager(x):
            return x[0], x[1] / count

        js_bool = 'true' if cls.inverse else 'false'

        if on_avg:
            if cls.inverse:
                def inverse_filt(x):
                    return cls.is_excluded(x[0]) or x[1] < cls.threshold and \
                           x[0] not in cls.keep_tags
                iter = filter(inverse_filt, map(averager, cls.tags.items()))
            else:
                def filt(x):
                    return not cls.is_excluded(x[0]) and \
                           (x[1] >= cls.threshold or x[0] in cls.keep_tags)
                iter = filter(filt,  map(averager, cls.tags.items()))
        else:
            iter = map(averager, cls.tags.items())

        for k, already_averaged_val in iter:
            tags[k] = already_averaged_val
            # trigger an event to place the tag in the active tags list
            tags_str += f""", <a href='javascript:tag_clicked("{k}", {js_bool})'>{k}</a>"""

        for ent, val in cls.ratings.items():
            ratings[ent] = val / count

        print('all done :)')
        return (tags_str[2:], ratings, tags, '')
