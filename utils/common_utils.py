import os, sys, json
from os.path import join, basename, dirname, exists, isdir, splitext
from os import makedirs, listdir, sep


def load_json(path):
    try:
        with open(path, 'rb') as f:
            json_data = json.loads(f.read().decode('utf-8'))
    except Exception as e:
        print('Failed to load %s (%s)' % (path, e))
        raise e
    return json_data


def dump_json(json_data, path, use_jsview=True):
    print('Dumping %s' % path)

    with open(path, 'wb') as f:
        if use_jsview:
            from jsview import tobuffer as jsview_tobuffer
            json_str = ''.join(jsview_tobuffer(json_data, [], width=90, indent=2))
        else:
            json_str = json.dumps(json_data, indent=2, sort_keys=True, ensure_ascii=False)

        f.write(json_str.encode('utf-8'))


def create_directory(path):
    if not exists(path):
        makedirs(path)


def rename_dict_recursive(root, rename_dict, ignore_missing=False):
    if not isinstance(root, dict):
        return

    for k, v in root.items():
        if isinstance(v, dict):
            rename_dict_recursive(v, rename_dict, ignore_missing)
        else:
            if k in rename_dict:
                if ignore_missing:
                    if v in rename_dict[k]:
                        root[k] = rename_dict[k][v]
                else:
                    root[k] = rename_dict[k][v]


def replace_recursive(root, replace_dict):
    if isinstance(root, dict):
        for k, v in root.items():
            if isinstance(v, dict) or isinstance(v, list):
                replace_recursive(v, replace_dict)
            else:
                if k in replace_dict:
                    if len(replace_dict[k]) == 0:
                        del root[k]
                    else:
                        root[k] = replace_dict[k]
    elif isinstance(root, list):
        for v in root:
            if isinstance(v, dict) or isinstance(v, list):
                replace_recursive(v, replace_dict)
