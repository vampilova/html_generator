from argparse import ArgumentParser
from utils.common_utils import load_json
from os.path import dirname, join, isfile, splitext
from yattag import Doc
from base64 import b64encode
from PIL import Image
from io import BytesIO
from textwrap import wrap
import pycountry
import sys, json


special_mrz = ['mrp', 'mrva', 'mrvb', 'td1', 'td2']
special_doc = ['special_mrz', 'card', 'barcode', 'xpo', 'abk', 'gbd', 'rks', 'uap', 'xec', 'xom', 'eu.medcard']
ignore_list = ['document_crop', 'mrz_mobile_new']
special_doc_dict = {"special_mrz": "Special mrz", 
                    "card": "Card",
                    "barcode": "Barcode",
                    "xpo": "Interpol documents",
                    "abk": "Abkhazia",
                    "gbd": "Cayman Islands",
                    "rks": "The Republic of Kosovo",
                    "uap": "The African Union",
                    "xec": "Economic Community of West African States — ECOWAS",
                    "xom": "The Sovereign Military Order of Malta",
                    "eu.medcard": "EU Medcard"
                    }

def print_warning(path, message, quiet):
    if not quiet:
        print('WARNING [%s]: \t %s' % (message, path))


def relative_join(a, b, root_dir):
    if b.startswith(':/'):
        return join(root_dir, b[2:])
    else:
        return join(dirname(a), b)


def escape_root_path(path):
    if path.startswith(':/'):
        return path.replace(':/', '')
    return path


def get_all_countries(bundle_json_path, root_dir):
    docfiles = []
    bundle_json = load_json(bundle_json_path)
    for name, e in bundle_json['engines'].items():
        engine = load_json(join(dirname(bundle_json_path), escape_root_path(e['path'])))
        for d in engine['documents']:
            if d.split('/')[-1].split('.')[0] not in ignore_list:
                if d.split('/')[-1].split('.')[0] == 'mrz':
                    mrz_engine = load_json(join(dirname(bundle_json_path), escape_root_path(d)))
                    for mrz_d in mrz_engine['mrz']['(documentations)']:
                        if mrz_d.split('.')[1] in special_mrz:
                            name = 'special_mrz'
                        else:
                            name = mrz_d.split('.')[1]
                    if name not in docfiles:
                        docfiles.append(name)
                elif d.split('/')[-1].split('.')[0] == 'eu':
                    if d.split('/')[-1].split('.')[1] =='payslip':
                        print(d.split('/')[-1])
                        name = d.split('/')[-1].split('.')[2]
                        print(name)
                        if name not in docfiles:
                            docfiles.append(name)
                    if d.split('/')[-1].split('.')[1] =='medcard':
                        name = '.'.join(d.split('/')[-1].split('.')[:2])
                        if name not in docfiles:
                            docfiles.append(name)
                else:
                    name = d.split('/')[-1].split('.')[0]
                    if name not in docfiles:
                        docfiles.append(name)
    return docfiles


def get_all_docs_files_paths(bundle_json_path, root_dir):
    docfiles = []
    bundle_json = load_json(bundle_json_path)
    for name, e in bundle_json['engines'].items():
        engine = load_json(join(dirname(bundle_json_path), escape_root_path(e['path'])))
        docfiles.extend([relative_join(bundle_json_path, d, root_dir)
                         for d in engine['documents']])
    return docfiles


def get_image_base64(image_path, max_size=None):
    if max_size is not None:
        im = Image.open(image_path)
        im.thumbnail((max_size, max_size), Image.ANTIALIAS)
        im = im.convert('RGB')
        file_io = BytesIO()
        im.save(file_io, 'JPEG')
        file_io.seek(0)
        return b64encode(file_io.read())
    else:
        with open(image_path, 'rb') as f:
            return b64encode(f.read())


def parse_docs_file(docsfile_path, root_dir, quiet):
    docsfile = load_json(docsfile_path)
    docsfile_reference = {}
    name_doc_pairs = []

    for name, doc in docsfile.items():
        if isinstance(doc['output_fields'], list):
            name_doc_pairs.append((name, doc))
        elif isinstance(doc['output_fields'], dict):
            for key in doc['output_fields'].keys():
                name_doc_pairs.append((key, doc))
        else:
            raise Exception('Cannot understand the output fields format: %s' % str(doc['output_fields']))

    for name, doc in name_doc_pairs:
        output_fields = doc['output_fields']
        image_fields = []
        if isinstance(output_fields, dict):
            output_fields = doc['output_fields'][name]

        for tpl_name, tpl_dict in doc['templates'].items():
            tpl_path = relative_join(docsfile_path, tpl_dict['path'], root_dir)
            tpl = load_json(tpl_path)[tpl_name]

            for field_name, v in tpl['fields'].items():
                workflow = v['workflow']
                f = workflow if isinstance(workflow, dict) \
                    else load_json(relative_join(tpl_path, workflow, root_dir))
                if f['type'] == 'image' and field_name in output_fields:
                    image_fields.append(field_name)
                if f['type'] == 'dummy' and field_name == 'photo' and name.startswith('mrz.') and field_name in output_fields:
                    image_fields.append(field_name)

        ret = {
            'templates': {},
            'image_fields': sorted(image_fields),
            'string_fields': sorted([f for f in output_fields if f not in image_fields]),
        }

        if '(documentation)' in doc:
            ret.update(doc['(documentation)'])
            if 'description' not in doc['(documentation)']:
                print_warning(docsfile_path, 'no description in (documentation)', quiet)
        elif '(documentations)' in doc:
            ret.update(doc['(documentations)'][name])
            if 'description' not in doc['(documentations)'][name]:
                print_warning(docsfile_path, 'no description in (documentations)[%s]' % name, quiet)
        else:
            print_warning(docsfile_path, 'no (documentation)', quiet)

        for tpl_name, tpl_dict in doc['templates'].items():
            tpl_path = relative_join(docsfile_path, tpl_dict['path'], root_dir)
            tpl = load_json(tpl_path)[tpl_name]

            if not tpl.get('key', True):
                continue

            template_config_path = relative_join(tpl_path, tpl['config'], root_dir)
            template_config = load_json(template_config_path)

            ret['templates'][tpl_name] = {}
            sample_path = relative_join(template_config_path, template_config['(sample)'], root_dir)
            if isfile(sample_path):
                ret['templates'][tpl_name]['sample'] = sample_path
                ret['templates'][tpl_name]['sample_base64'] = get_image_base64(sample_path,max_size=256)

        docsfile_reference[name] = ret

    return docsfile_reference


def generate_documents_reference_html(countries, docs, embed_images):
    doc, tag, text = Doc().tagtext()

    json_reference = []

    with tag('html'):
        with tag('head'):
            doc.asis('<link rel="stylesheet" href="./css/style.css">')
            with tag('title'):
                text('Smart ID Engine Documents Reference')
            with tag('script'):
                doc.asis('function topFunction() { document.body.scrollTop = 0; document.documentElement.scrollTop = 0;}')
        
        with tag('body'):
            with tag('input', klass='button_top', type="button", name="top", value="Top", onclick="topFunction()"):
                with tag('h1', align='center'):
                    text('List of countries and special type of documents in this bundle')
            with tag('ul', klass='list3b'):
                for country in sorted(countries):
                    with tag('li'):
                        with tag('a', href='#'+country):
                            if country not in special_doc:
                                country_code_href = pycountry.countries.get(alpha_3=country).name
                            else:
                                country_code_href = special_doc_dict[country]
                            text(country_code_href)
            with tag('table', klass='table'):
                with tag('tr'):
                    with tag('th'):
                        text('Document type')
                    with tag('th'):
                        text('Document description')
                    with tag('th'):
                        text('PRADO link')
                    with tag('th'):
                        text('String fields')
                    with tag('th'):
                        text('Image fields')
                    with tag('th'):
                        text('Templates')

                for country in sorted(countries):
                    with tag('tr'):
                        with tag('td', colspan="7", style="font-size: 18px; text-align:center; font-weight: bold;"):
                            with tag('a', name=country):
                                if country not in special_doc:
                                    country_code = pycountry.countries.get(alpha_3=country).name
                                else:
                                    country_code = special_doc_dict[country]
                                text(country_code)
                    for i_doc, (doc_type, doc_reference) in enumerate(sorted(docs.items())):
                        if doc_type.split('.')[0] == 'mrz':
                            if doc_type.split('.')[1] not in special_mrz:
                                doc_type_country = doc_type.split('.')[1]
                            else:
                                doc_type_country = 'special_mrz'
                        elif '.'.join(doc_type.split('.')[:2]) == 'eu.payslip':
                            doc_type_country = doc_type.split('.')[2]
                        elif '.'.join(doc_type.split('.')[:2]) == 'eu.medcard':
                            doc_type_country = '.'.join(doc_type.split('.')[:2])
                        else: 
                            doc_type_country = doc_type.split('.')[0]
                        if country == doc_type_country:
                            json_row = {}
                                 
                            with tag('tr'):
                                with tag('td'):
                                    with tag('code'):
                                        text(doc_type)
                                        json_row['document_code'] = doc_type
                                        if doc_type.split('.')[0] not in ["barcode", "card", "crop", "eu", "mrz"]:
                                            json_row['iso_country_code'] = doc_type.split('.')[0]
        
                                with tag('td'):
                                    if 'description' in doc_reference:
                                        wrapped_description = wrap(doc_reference['description'], 60)
                                        text('\n'.join(wrapped_description))
                                        json_row['description'] = doc_reference['description']
        
                                with tag('td'):
                                    if 'prado_link' in doc_reference:
                                        prado_links = doc_reference['prado_link']
                                        if not isinstance(prado_links, list):
                                            prado_links = [prado_links]
                                        for i, prado_link in enumerate(prado_links):
                                            with tag('a', href=prado_link, style = "color: #4e7470; text-decoration: none;", onmouseover = "this.style.color='#6ebfb4';", onmouseout = "this.style.color='#4e7470';"):
                                                text('PRADO link')
                                            text('\n')
                                        json_row['prado_links'] = prado_links
        
                                with tag('td'):
                                    if 'string_fields' in doc_reference:
                                        text('\n'.join(doc_reference['string_fields']))
                                        json_row['string_fields'] = doc_reference['string_fields']
        
                                with tag('td'):
                                    if 'image_fields' in doc_reference:
                                        text('\n'.join(doc_reference['image_fields']))
                                        json_row['image_fields'] = doc_reference['image_fields']
        
                                with tag('td'):
                                    tpl_names = []
                                    for tpl_name, tpl_reference in sorted(doc_reference['templates'].items()):
                                        # if 'sample' in tpl_reference:
                                        #     with tag('a', href=tpl_reference['sample']):
                                        #         text(tpl_name + '\n')
                                        if 'sample_base64' in tpl_reference and embed_images:
                                            src_suffix = 'data:image/%s;base64,%s' % (
                                                'jpeg',
                                                str(tpl_reference['sample_base64'].decode('ascii')),
                                            )
                                            with tag('img',
                                                     src=src_suffix,
                                                     title=tpl_name,
                                                     ):
                                                text('\n')
                                        else:
                                            text(tpl_name + '\n')
                                        tpl_names.append(tpl_name)
                                    json_row['templates'] = tpl_names
    
                        json_reference.append(json_row)

    return doc.getvalue(), json_reference


def main():
    parser = ArgumentParser()
    parser.add_argument('--bundle', type=str,
                        default='../data/bundle_international_mobile.json')
    parser.add_argument('--out-html', type=str,
                        default='../core/smartid_wrap/smartIdEngine/doc/DOCUMENTS_REFERENCE.html')
    parser.add_argument('--out-json', type=str, default='')
    parser.add_argument('--quiet', '-q', help='disable warnings messages',
                        action='store_true')
    parser.add_argument('--images', '-i', help='embed images', action='store_true')

    args = parser.parse_args()

    bundle_path, root_dir = args.bundle, dirname(args.bundle)

    all_countries_paths = get_all_countries(bundle_path, root_dir)
    for country in all_countries_paths:
        code = ""
        try:
            code = pycountry.countries.get(alpha_3=country).name
        except Exception:
            print('Not supported: ', country)
        print('code: ', country, '- country:', code)

    docs_files_paths = get_all_docs_files_paths(bundle_path, root_dir)

    documents_reference = {}

    for docsfile in docs_files_paths:
        docsfile_reference = parse_docs_file(docsfile, root_dir, args.quiet)
        documents_reference.update(docsfile_reference)

    html, json_ref = generate_documents_reference_html(all_countries_paths, documents_reference, args.images)

    with open(args.out_html, 'w', encoding = 'utf-8') as f:
        f.write(html)

    if args.out_json != '':
        with open(args.out_json, 'w', encoding = 'utf-8') as js:
            js.write(json.dumps(json_ref, indent = 2, ensure_ascii = False))

if __name__ == '__main__':
    main()