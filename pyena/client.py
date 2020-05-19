import os
import argparse
import sys
import requests
from ftplib import FTP, FTP_TLS
from socket import timeout
from datetime import datetime
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup as bs         # pip install bs4 lxml

from .util import hashfile

WEBIN_USER = os.environ.get('WEBIN_USER')
WEBIN_PASS = os.environ.get('WEBIN_PASS')


def _add_today(center_name):
    return '''
    <SUBMISSION center_name="''' + center_name + '''">
    <ACTIONS>
        <ACTION>
            <ADD/>
        </ACTION>
        <ACTION>
            <HOLD HoldUntilDate="%s" />
        </ACTION>
    </ACTIONS>
    </SUBMISSION>
    ''' % datetime.today().strftime('%Y-%m-%d')

def _release_target(target, center_name, real=False):
    release_xml = '''
    <SUBMISSION center_name="''' + center_name + '''">
    <ACTIONS>
        <ACTION>
            <RELEASE target="%s" />
        </ACTION>
    </ACTIONS>
    </SUBMISSION>
    ''' % target
    if real:
        return requests.post("https://www.ebi.ac.uk/ena/submit/drop-box/submit/",
                files={
                    'SUBMISSION': release_xml,
                }, auth=HTTPBasicAuth(WEBIN_USER, WEBIN_PASS))
    else:
        return requests.post("https://wwwdev.ebi.ac.uk/ena/submit/drop-box/submit/",
                files={
                    'SUBMISSION': release_xml,
                }, auth=HTTPBasicAuth(WEBIN_USER, WEBIN_PASS))

def status_code(response_text):
    response = 0
    return response

def handle_response(status_code, content, accession=False):
    """Returns -1 if the response failed entirely, 0 if appears OK, and 1 if appears incorrect"""
    response_code = -1
    response_accession = None

    if status_code != 200:
        # NOT 200
        sys.stderr.write("\n".join([
            '*' * 80,
            "ENA responded with HTTP %s." % status_code,
            "I don't know how to handle this. For your information, the response is below:",
            '*' * 80,
            content,
            '*' * 80,
            ]))
        response_code = -1
    else:
        # OK 200
        soup = bs(content, 'xml')
        if len(soup.findAll("ERROR")) > 0:
            # See if this is a duplicate accession before blowing up
            for error in soup.findAll("ERROR"):
                if "already exists in the submission account with accession:" in error.text:
                    response_accession = error.text.split()[-1].replace('"', "").replace('.', "")
                    response_code = 1
                    sys.stderr.write("[SKIP] Accession %s already exists. Moving on...\n" % response_accession)
                    break
                elif "has already been submitted and is waiting to be processed" in error.text:
                    #response_accession = error.text.split()[1].replace("object(", "").replace(")", "")
                    response_accession = error.text.split()[4]
                    response_code = 1
                    sys.stderr.write("[SKIP] File %s already uploaded. Cannot release again. Moving on...\n" % response_accession)
                    break
            if not response_accession:
                sys.stderr.write("\n".join([
                    '*' * 80,
                    "ENA responded with HTTP 200, but there were ERROR messages in the response.",
                    "I don't know how to handle this. For your information, the response is below:",
                    '*' * 80,
                    content,
                    '*' * 80,
                ]))
                response_code = -1
        else:
            if accession:
                # Try and parse an accession
                try:
                    response_accession = soup.find(accession).get("accession")
                except:
                    pass
            response_code = 0

    return response_code, response_accession


def submit_today(submit_type, payload, center_name, release_asap=False, real=False):
    files = {}
    files[submit_type] = payload
    files["SUBMISSION"] = _add_today(center_name)

    if real:
        r = requests.post("https://www.ebi.ac.uk/ena/submit/drop-box/submit/",
                files=files,
                auth=HTTPBasicAuth(WEBIN_USER, WEBIN_PASS))
    else:
        r = requests.post("https://wwwdev.ebi.ac.uk/ena/submit/drop-box/submit/",
                files=files,
                auth=HTTPBasicAuth(WEBIN_USER, WEBIN_PASS))
    #print(payload)
    #print(_add_today())
    status, accession = handle_response(r.status_code, r.text, accession=submit_type)
    if release_asap and status == 0:
        r = _release_target(accession, center_name, real=real)
        status, _ = handle_response(r.status_code, r.text)
        if status == 0:
            sys.stderr.write("[INFO] %s released successfully: %s\n" % (submit_type, accession))

    return status, accession

def register_sample(sample_alias, taxon_id, center_name, attributes={}, real=False):
    s_attributes = "\n".join(["<SAMPLE_ATTRIBUTE><TAG>%s</TAG><VALUE>%s</VALUE></SAMPLE_ATTRIBUTE>" % (k, v) for k,v in attributes.items() if v is not None])

    s_xml = '''
    <SAMPLE_SET>
    <SAMPLE alias="''' + sample_alias + '''" center_name="''' + center_name + '''">
    <TITLE>''' + sample_alias + '''</TITLE>
    <SAMPLE_NAME>
      <TAXON_ID>''' + taxon_id + '''</TAXON_ID>
    </SAMPLE_NAME>
    <SAMPLE_ATTRIBUTES>''' + s_attributes + '''</SAMPLE_ATTRIBUTES>
    </SAMPLE>
    </SAMPLE_SET>
    '''

    return submit_today("SAMPLE", s_xml, center_name, release_asap=True, real=real)

def register_experiment(exp_alias, study_accession, sample_accession, instrument, library_d, center_name, real=False):
    platform_stanza = ""

    instrument = instrument.lower()
    if instrument == "miseq":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina MiSeq</INSTRUMENT_MODEL></ILLUMINA>"
    elif instrument == "hiseq 2500":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina HiSeq 2500</INSTRUMENT_MODEL></ILLUMINA>"
    elif instrument == "nextseq 550":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina NextSeq 550</INSTRUMENT_MODEL></ILLUMINA>"
    elif instrument == "nextseq":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina NextSeq</INSTRUMENT_MODEL></ILLUMINA>"
    elif instrument == "novaseq":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina NovaSeq</INSTRUMENT_MODEL></ILLUMINA>"
    elif instrument == "minion":
        platform_stanza ="<OXFORD_NANOPORE><INSTRUMENT_MODEL>MinION</INSTRUMENT_MODEL></OXFORD_NANOPORE>"
    elif instrument == "gridion":
        platform_stanza ="<OXFORD_NANOPORE><INSTRUMENT_MODEL>GridION</INSTRUMENT_MODEL></OXFORD_NANOPORE>"
        #design_stanza = "<DESIGN_DESCRIPTION>FLO-MIN106 R9.4.1C FlipFlop</DESIGN_DESCRIPTION>"
    elif instrument == "promethion":
        platform_stanza ="<OXFORD_NANOPORE><INSTRUMENT_MODEL>PromethION</INSTRUMENT_MODEL></OXFORD_NANOPORE>"
    else:
        sys.stderr.write("[FAIL] Unable to construct platform stanza for experiment %s with instrument %s\n" % (exp_alias, instrument))
        return -1, None

    pair_size = 0
    layout_stanza = []

    if pair_size:
        layout_stanza.append("<PAIRED />") # NOMINAL_LENGTH=\"%d\"/>" % pair_size)
    else:
        layout_stanza.append("<SINGLE />")


    e_xml = '''
    <EXPERIMENT_SET>
    <EXPERIMENT alias="''' + exp_alias + '''" center_name="''' + center_name + '''">
       <TITLE>''' + exp_alias + '''</TITLE>
       <STUDY_REF accession="''' + study_accession + '''"/>
       <DESIGN>
           <DESIGN_DESCRIPTION/>
           <SAMPLE_DESCRIPTOR accession="''' + sample_accession + '''"/>
           <LIBRARY_DESCRIPTOR>
               <LIBRARY_NAME/>
               <LIBRARY_STRATEGY>''' + library_d["strategy"] + '''</LIBRARY_STRATEGY>
               <LIBRARY_SOURCE>''' + library_d["source"] + '''</LIBRARY_SOURCE>
               <LIBRARY_SELECTION>''' + library_d["selection"] + '''</LIBRARY_SELECTION>
               <LIBRARY_LAYOUT>''' + "".join(layout_stanza) + '''</LIBRARY_LAYOUT>
           </LIBRARY_DESCRIPTOR>
       </DESIGN>
       <PLATFORM>''' + platform_stanza + '''
       </PLATFORM>
       <EXPERIMENT_ATTRIBUTES>

       </EXPERIMENT_ATTRIBUTES>
    </EXPERIMENT>
    </EXPERIMENT_SET>
    '''

    # Register experiment to add run to
    return submit_today("EXPERIMENT", e_xml, center_name, release_asap=True, real=real)

def register_run(run_alias, fn, exp_accession, center_name, fn_type="bam", real=False):
    try:
        ftp = FTP('webin.ebi.ac.uk', user=WEBIN_USER, passwd=WEBIN_PASS, timeout=30)
        ftp.storbinary('STOR %s' % os.path.basename(fn), open(fn, 'rb'))
        ftp.quit()
    except Exception as e:
        sys.stderr.write("[FAIL] FTP transfer timed out or failed for %s\n%s" % (fn, e))
        return -1, None

    fn_checksum = hashfile(fn)

    r_xml = '''
    <RUN_SET>
        <RUN alias="''' + run_alias + '''" center_name="''' + center_name + '''">
            <EXPERIMENT_REF accession="''' + exp_accession + '''"/>
            <DATA_BLOCK>
                <FILES>
                    <FILE filename="''' + os.path.basename(fn) + '''" filetype="''' + fn_type + '''" checksum_method="MD5" checksum="''' + fn_checksum + '''" />
                </FILES>
            </DATA_BLOCK>
        </RUN>
    </RUN_SET>
    '''
    return submit_today("RUN", r_xml, center_name, release_asap=True, real=real)

def cli():
    parser = argparse.ArgumentParser()

    parser.add_argument("--my-data-is-ready", action="store_true")

    parser.add_argument("--study-accession", required=True)

    parser.add_argument("--sample-attr", action='append', nargs=2, metavar=('tag', 'value'))
    parser.add_argument("--sample-name", required=True)
    parser.add_argument("--sample-center-name", required=True)
    parser.add_argument("--sample-taxon", required=False, default="2697049")

    parser.add_argument("--run-name", required=True)
    parser.add_argument("--run-file-path", required=True)
    parser.add_argument("--run-file-type", required=False, default="bam")
    parser.add_argument("--run-center-name", required=True)
    parser.add_argument("--run-instrument", required=True)
    parser.add_argument("--run-lib-source", required=True)
    parser.add_argument("--run-lib-selection", required=True)
    parser.add_argument("--run-lib-strategy", required=True)


    args = parser.parse_args()

    sample_accession = exp_accession = run_accession = None
    success = 0

    sample_stat, sample_accession = register_sample(args.sample_name, args.sample_taxon, args.sample_center_name, {x[0]: x[1] for x in args.sample_attr}, real=args.my_data_is_ready)
    if sample_stat >= 0:
        exp_stat, exp_accession = register_experiment("%s/%s" % (args.sample_name, args.run_name), args.study_accession, sample_accession, args.run_instrument.replace("_", " "), library_d={
            "source": args.run_lib_source.replace("_", " "),
            "selection": args.run_lib_selection.replace("_", " "),
            "strategy": args.run_lib_strategy.replace("_", " "),
        }, center_name=args.run_center_name, real=args.my_data_is_ready)
        if exp_stat >= 0:
            run_stat, run_accession = register_run(args.run_name, args.run_file_path, exp_accession, center_name=args.run_center_name, fn_type=args.run_file_type, real=args.my_data_is_ready)
            if run_stat >= 0 and run_accession:
                success = 1

    sys.stdout.write(" ".join([str(x) for x in [
        success,
        1 if args.my_data_is_ready else 0,
        args.sample_name,
        args.run_name,
        args.run_file_path,
        args.study_accession,
        sample_accession,
        exp_accession,
        run_accession
    ]]) + '\n')
