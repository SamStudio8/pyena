import os
import sys
import requests
from ftplib import FTP, FTP_TLS
from socket import timeout
from datetime import datetime
from requests.auth import HTTPBasicAuth
from bs4 import BeautifulSoup as bs         # pip install bs4 lxml

WEBIN_USER = os.environ.get('WEBIN_USER')
WEBIN_PASS = os.environ.get('WEBIN_PASS')


def _add_today():
    return '''
    <SUBMISSION center_name="center">
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

def _release_target(target):
    release_xml = '''
    <SUBMISSION center_name="center">
    <ACTIONS>
        <ACTION>
            <RELEASE target="%s" />
        </ACTION>
    </ACTIONS>
    </SUBMISSION>
    ''' % target
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
        print('*' * 80)
        print("ENA responded with HTTP %s." % status_code)
        print("I don't know how to handle this. For your information, the response is below:")
        print('*' * 80)
        print(content)
        print('*' * 80)
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
                    print("Accession %s already exists. Moving on..." % response_accession)
                    break
                elif "has already been submitted and is waiting to be processed" in error.text:
                    response_accession = error.text.split()[1].replace("object(", "").replace(")", "")
                    response_code = 1
                    print("Accession %s already exists. Moving on..." % response_accession)
                    break
            if not response_accession:
                print('*' * 80)
                print("ENA responded with HTTP 200, but there were ERROR messages in the response.")
                print("I don't know how to handle this. For your information, the response is below:")
                print('*' * 80)
                print(content)
                print('*' * 80)
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


def submit_today(submit_type, payload, release_asap=False):
    files = {}
    files[submit_type] = payload
    files["SUBMISSION"] = _add_today()
    r = requests.post("https://wwwdev.ebi.ac.uk/ena/submit/drop-box/submit/",
            files=files,
            auth=HTTPBasicAuth(WEBIN_USER, WEBIN_PASS))
    print(payload)
    print(_add_today())
    status, accession = handle_response(r.status_code, r.text, accession=submit_type)
    if release_asap and status == 0:
        r = _release_target(accession)
        status, _ = handle_response(r.status_code, r.text)
        if status == 0:
            print("[INFO] %s released successfully: %s" % (submit_type, accession))

    return status, accession

def register_sample(sample_alias, taxon_id, centre_name):
    s_xml = '''
    <SAMPLE_SET>
    <SAMPLE alias="''' + sample_alias + '''" center_name="''' + centre_name + '''">
    <TITLE>sample_title</TITLE>
    <SAMPLE_NAME>
      <TAXON_ID>''' + taxon_id + '''</TAXON_ID>
    </SAMPLE_NAME>
    </SAMPLE>
    </SAMPLE_SET>
    '''

    return submit_today("SAMPLE", s_xml, release_asap=True)

def register_experiment(exp_alias, study_accession, sample_accession, instrument, strategy, source, selection):
    platform_stanza = ""

    if instrument == "miseq":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina MiSeq</INSTRUMENT_MODEL></ILLUMINA>"
    if instrument == "hiseq2000":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina HiSeq 1500</INSTRUMENT_MODEL></ILLUMINA>"
    if instrument == "hiseq2000":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina HiSeq 2000</INSTRUMENT_MODEL></ILLUMINA>"
    if instrument == "hiseq4000":
        platform_stanza = "<ILLUMINA><INSTRUMENT_MODEL>Illumina HiSeq 4000</INSTRUMENT_MODEL></ILLUMINA>"
    elif instrument == "grid":
        platform_stanza ="<OXFORD_NANOPORE><INSTRUMENT_MODEL>GridION</INSTRUMENT_MODEL></OXFORD_NANOPORE>"
        #design_stanza = "<DESIGN_DESCRIPTION>FLO-MIN106 R9.4.1C FlipFlop</DESIGN_DESCRIPTION>"
    elif instrument == "prom":
        platform_stanza ="<OXFORD_NANOPORE><INSTRUMENT_MODEL>PromethION</INSTRUMENT_MODEL></OXFORD_NANOPORE>"

    pair_size = 0
    layout_stanza = []

    if pair_size:
        layout_stanza.append("<PAIRED />") # NOMINAL_LENGTH=\"%d\"/>" % pair_size)
    else:
        layout_stanza.append("<SINGLE />")


    e_xml = '''
    <EXPERIMENT_SET>
    <EXPERIMENT alias="''' + exp_alias + '''" center_name="my centre">
       <TITLE>RUN OF SAMPLES</TITLE>
       <STUDY_REF accession="''' + study_accession + '''"/>
       <DESIGN>
           <DESIGN_DESCRIPTION/>
           <SAMPLE_DESCRIPTOR accession="''' + sample_accession + '''"/>
           <LIBRARY_DESCRIPTOR>
               <LIBRARY_NAME/>
               <LIBRARY_STRATEGY>''' + strategy + '''</LIBRARY_STRATEGY>
               <LIBRARY_SOURCE>''' + source + '''</LIBRARY_SOURCE>
               <LIBRARY_SELECTION>''' + selection + '''</LIBRARY_SELECTION>
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
    return submit_today("EXPERIMENT", e_xml, release_asap=True)

def register_run(run_alias, fn, exp_accession, fn_checksum, fn_type="bam"):
    try:
        ftp = FTP('webin.ebi.ac.uk', user=WEBIN_USER, passwd=WEBIN_PASS, timeout=30)
        ftp.storbinary('STOR %s' % fn, open(fn, 'rb'))
        ftp.quit()
    except timeout:
        print("BOOOOOOO")

    r_xml = '''
    <RUN_SET>
        <RUN alias="''' + run_alias + '''" center_name="my centre">
            <EXPERIMENT_REF accession="''' + exp_accession + '''"/>
            <DATA_BLOCK>
                <FILES>
                    <FILE filename="''' + fn + '''" filetype="''' + fn_type + '''" checksum_method="MD5" checksum="''' + fn_checksum + '''" />
                </FILES>
            </DATA_BLOCK>
        </RUN>
    </RUN_SET>
    '''
    return submit_today("RUN", r_xml, release_asap=True)

def cli():
    import argparse

    project_accession = os.environ.get('WEBIN_STUDY')
    sample_stat, sample_accession = register_sample('sdfkasdjflkasdjflkasdjf', '2697049', 'my cool test centre')

    #if sample_stat:
    #    exp_stat, exp_accession = register_experiment('alias', project_accession, sample_accession, 'miseq', 'AMPLICON', 'VIRAL RNA', 'PCR')
    #   if exp_stat:
    #       run_stat, run_accession = register_run('alias', 'test.bam', exp_accession, fn_type="bam", fn_checksum="b1946ac92492d2347c6235b4d2611184")

    print(project_accession, sample_accession, exp_accession, run_accesison)