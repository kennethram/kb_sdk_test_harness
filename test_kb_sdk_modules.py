#!/usr/bin/python3

import sys
import os
import shutil
import errno
import uuid
import subprocess
import re
from datetime import datetime


# ISO timestamp
def now_ISO():
    now_timestamp = datetime.now()
    now_secs_from_epoch = (now_timestamp - datetime(1970,1,1)).total_seconds()
    now_timestamp_in_iso = datetime.fromtimestamp(int(now_secs_from_epoch)).strftime('%Y-%m-%d_%H-%M-%S')
    return now_timestamp_in_iso

# mkdir -p that works for py3 and py2.7
def mkdirs_fullpath (path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >= 2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

# chirp: timstamped msg
def chirp (msg, prog=None):
    peep = "["+now_ISO()+"]"
    if prog:
        peep += "["+prog+"]"
    print (peep+" "+msg)
        
        
# install test_local template
def install_test_local_template (test_config_file, module_name, template_path, template_name, module_path):
    # initial copy
    template_src = os.path.join (template_path, template_name)
    template_dst = os.path.join (module_path, template_name)
    shutil.copytree(template_src, template_dst)

    # add test.cfg
    shutil.copy(test_config_file,os.path.join(module_path,template_name,'test.cfg'))

    # fix module name in run_test.sh and run_bash.sh
    for f_name in ['run_bash.sh', 'run_tests.sh']:
        revised_buf = []
        f_path = os.path.join(template_dst,f_name)
        with open (f_path,'r') as fh:
            for line in fh.readlines():
                revised_buf.append(line.replace('%%MODULE_NAME%%',module_name.lower()))
        with open (f_path,'w') as fh:
            fh.write(''.join(revised_buf))

            
# run subprocess
#   Note: command is a list of command line args with no whitespace
def run_subprocess(runcmd=None, rundir=None, runlog=None, begdir=None, ignore_error=False):
    if begdir:
        os.chdir (rundir)
        os.environ['PWD'] = rundir
        #rundir = '.'
    runbuf = []
    p = subprocess.Popen(runcmd, \
                         cwd = rundir, \
                         stdout = subprocess.PIPE, \
                         stderr = subprocess.STDOUT, \
                         shell = None)
                         #shell = True)

    if runlog:
        runlog_handle = open (runlog, 'w')

    while True:
        line = p.stdout.readline().decode()
        if not line: break
        if runlog:
            runlog_handle.write(line)
            runlog_handle.flush()
        line = line.rstrip()
        print (line)
        runbuf.append(line)
    p.stdout.close()
    p.wait()

    if begdir:
        os.chdir(begdir)
        os.environ['PWD'] = begdir
    if runlog:
        runlog_handle.close()

    if p.returncode != 0:
        if ignore_error:
            print ('ALERT: '+" ".join(runcmd)+'. return code: '+str(p.returncode))
        else:
            raise ValueError('ABORT: '+" ".join(runcmd)+'. return code: '+str(p.returncode))
    
    return runbuf


# parse_command_line()
def parse_command_line(argv):
    params = dict()

    # paths
    if len(argv) < 3:
        print ("Usage: "+argv[0]+" <module_config> <sdk_login_config> [basepath]")
        sys.exit(-1)
    prog = re.sub ('^.*/', '', argv[0])
    module_config_file = argv[1]
    sdk_login_config_file = argv[2]
    if len(argv) > 3:
        base_path = argv[3]
    else:
        base_path = '.'
    if base_path.startswith('.'):
        base_path = os.path.join(os.getcwd(), base_path)
        base_path = re.sub ('^/mnt/.*/homes/'+os.environ['USER'], os.environ['HOME'], base_path)

    params['program_name'] = prog
    params['module_config_file'] = module_config_file
    params['sdk_login_config_file'] = sdk_login_config_file
    params['base_path'] = base_path
    
    return params


# get_paths()
def get_paths (base_path):

    paths = dict()
    overall_run_timestamp = now_ISO()
    logs_dir    = os.path.join (base_path, 'logs', overall_run_timestamp)
    reports_dir = os.path.join (base_path, 'reports')
    module_exec_dir = os.path.join (base_path, 'module_exec', overall_run_timestamp)
    if not os.path.exists(logs_dir):
        mkdirs_fullpath(logs_dir)    
    if not os.path.exists(reports_dir):
        mkdirs_fullpath(reports_dir)    
    if not os.path.exists(module_exec_dir):
        mkdirs_fullpath(module_exec_dir)    

    template_path = os.path.join(base_path,'templates')
    template_name = 'test_local'
        
    paths['overall_run_timestamp'] = overall_run_timestamp
    paths['logs_dir'] = logs_dir
    paths['reports_dir'] = reports_dir
    paths['module_exec_dir'] = module_exec_dir
    paths['template_path'] = template_path
    paths['template_name'] = template_name
    
    return paths


# def get_module_info()
def  get_module_info (module_config_file, repo_basepath):
    module_info = dict()
    module_names = []
    module_repos = []  # not dict bacause may want to test different branches
    with open (module_config_file, 'r') as module_cfg_handle:
        for line in module_cfg_handle.readlines():
            line = line.strip()
            if line.startswith('#'):
                continue
            row = line.split()
            module_name = row[0]
            if len(row) < 2 or row[1] == '':
                repo_path = repo_basepath+'/'+module_name
            else:
                repo_path = row[1].replace('https://','')
                repo_path = repo_path.replace('http://','')
                
            module_names.append(module_name)
            module_repos.append(repo_path)

    module_info['module_names'] = module_names
    module_info['module_repos'] = module_repos

    return module_info


# initialize_report
def initialize_report (reports_dir, module_names, module_repos, overall_run_timestamp):
    report_info = dict()
    report_file = os.path.join(reports_dir, 'kb_sdk_unittests_'+overall_run_timestamp+'.tsv')
    report_buf = []
    if not os.path.exists(report_file):
        report_buf.append("\t".join(['#MODULE_NAME', 'REPO_LOC', 'P/F', 'TOTAL_TESTS', 'TESTS_PASSED', 'TESTS_FAILED', 'TESTS_SKIPPED', 'TOTAL_RUNTIME']))
        for mod_i,module_name in enumerate(module_names):
            report_buf.append("\t".join([module_name, module_repos[mod_i], '-', '-', '-','-','-','-']))
        with open(report_file, 'w') as report_handle:
            report_handle.write("\n".join(report_buf)+"\n")
    else:
        raise ValueError ("should not already have a report")

    report_info['report_file'] = report_file
    report_info['report_buf'] = report_buf

    return report_info


# update_report()
def update_report (report_file, report_buf, module_name, module_repo, test_scores):
    report_info = dict()
    new_report_buf = []
    if not os.path.exists(report_file):
        raise ValueError ("should already have a report to update")
    else:
        for line in report_buf:
            line = line.strip()
            if line.startswith("#"):
                new_report_buf.append(line)
                continue
            row = line.split()
            grade = row[2]
            if grade != '-':
                new_report_buf.append(line)
                continue
            this_module_name = row[0]
            this_module_repo = row[1]
            if this_module_name == module_name and this_module_repo == module_repo:
                for k in test_scores.keys():
                    if not test_scores[k]:
                        test_scores[k] = '0'
                new_report_buf.append("\t".join([module_name,
                                                 module_repo,
                                                 test_scores['grade'],
                                                 test_scores['total'],
                                                 test_scores['pass_cnt'],
                                                 test_scores['fail_cnt'],
                                                 test_scores['skip_cnt'],
                                                 test_scores['time']+'sec']))
            else:
                new_report_buf.append(line)
                
    with open(report_file, 'w') as report_handle:
        report_handle.write("\n".join(new_report_buf)+"\n")

    report_info['report_file'] = report_file
    report_info['report_buf'] = new_report_buf

    return report_info


# prep for subproc runs
def get_run_paths (module_names, module_repos, mod_i, module_exec_dir, logs_dir):
        run_info = dict()
        module_name = module_names[mod_i]
        module_repo = module_repos[mod_i]
        
        this_module_exec_timestamp = now_ISO()
        this_module_exec_dir = os.path.join (module_exec_dir, module_name+'_'+this_module_exec_timestamp)
        if not os.path.exists(this_module_exec_dir):
            mkdirs_fullpath(this_module_exec_dir)    

        # clone info
        stage = 'CLONE'
        clone_dir = this_module_exec_dir
        clone_cmd = ['git', 'clone', 'https://'+module_repo]
        clone_logs_dir = os.path.join(logs_dir, 'clone')
        if not os.path.exists(clone_logs_dir):
            mkdirs_fullpath(clone_logs_dir)    
        clone_log = os.path.join(clone_logs_dir, module_name+'_'+this_module_exec_timestamp+'-'+stage+'.log')

        # test info
        stage = 'TEST'
        test_dir = os.path.join(this_module_exec_dir, module_name)
        #test_dir = '.'
        test_cmd = ['kb-sdk', 'test']
        #test_cmd = ['ls', '-l']
        test_logs_dir = os.path.join(logs_dir, 'test')
        if not os.path.exists(test_logs_dir):
            mkdirs_fullpath(test_logs_dir)    
        test_log = os.path.join(test_logs_dir, module_name+'_'+this_module_exec_timestamp+'-'+stage+'.log')
        
        run_info['clone_dir'] = clone_dir
        run_info['clone_cmd'] = clone_cmd
        run_info['clone_log'] = clone_log
        run_info['test_dir'] = test_dir
        run_info['test_cmd'] = test_cmd
        run_info['test_log'] = test_log

        return run_info

    
def get_test_scores (test_runbuf):
    test_scores = dict()
    test_scores['grade'] = 'FAIL'
    test_scores['total'] = '0'
    test_scores['pass_cnt'] = '0'
    test_scores['fail_cnt'] = '0'
    test_scores['skip_cnt'] = '0'
    test_scores['time'] = '0'
    run_info_pattern = re.compile(r'Ran (\d+) tests? in ([\d\.]+)s')
    pass_skip_pattern = re.compile(r'OK \(SKIP=(\d+)\)')
    fail_skip_pattern = re.compile(r'FAILED \(SKIP=(\d+), errors=(\d+)\)')
    fail_error_failure_pattern = re.compile(r'FAILED \(errors=(\d+), failures=(\d+)\)')
    fail_error_pattern = re.compile(r'FAILED \(errors=(\d+)\)')
    i = 0
    for line in test_runbuf:
        m = run_info_pattern.match(line)
        if m:
            test_scores['total'] = m.group(1)
            test_scores['time'] = m.group(2)
            test_scores['time'] = str(int(float(test_scores['time'])+0.5))
        else:
            m = pass_skip_pattern.search(line)
            if m:
                test_scores['grade'] = 'PASS'
                test_scores['skip_cnt'] = m.group(1)
                test_scores['fail_cnt'] = '0'
            else:
                m = fail_skip_pattern.match(line)
                if m:
                    test_scores['grade'] = 'FAIL'
                    test_scores['skip_cnt'] = m.group(1)
                    test_scores['fail_cnt'] = m.group(2)
                else:
                    m = fail_error_failure_pattern.match(line)
                    if m:
                        test_scores['grade'] = 'FAIL'
                        test_scores['fail_cnt'] = str(int(m.group(1))+int(m.group(2)))
                        test_scores['skip_cnt'] = '0'
                    else:
                        m = fail_error_pattern.match(line)
                        if m:
                            test_scores['grade'] = 'FAIL'
                            test_scores['fail_cnt'] = m.group(1)
                            test_scores['skip_cnt'] = '0'
                        elif line.startswith('OK'):
                            test_scores['grade'] = 'PASS'
                            test_scores['skip_cnt'] = '0'
                            test_scores['fail_cnt'] = '0'
                        elif line.startswith('RESULT:OK'):
                            test_scores['grade'] = 'PASS'
                            test_scores['skip_cnt'] = '0'
                            test_scores['fail_cnt'] = '0'
                        elif line.startswith('FAILED'):
                            test_scores['grade'] = 'FAIL'
                            test_scores['skip_cnt'] = 'N/A'
                            test_scores['fail_cnt'] = 'N/A'

    if test_scores['pass_cnt'] == '0':
        if test_scores.get('fail_cnt') and test_scores['fail_cnt'] != 'N/A' \
           and test_scores.get('skip_cnt') and test_scores['skip_cnt'] != 'N/A':
            test_scores['pass_cnt'] = str(int(test_scores['total'])-int(test_scores['fail_cnt'])-int(test_scores['skip_cnt']))
        else:
            test_scores['pass_cnt'] = 'N/A'

    return test_scores                        
                        

# MAIN
def main(argv):

    # config
    params = parse_command_line (argv)
    prog                  = params['program_name']
    module_config_file    = params['module_config_file']
    sdk_login_config_file = params['sdk_login_config_file']
    base_path             = params['base_path']
    
    # output dirs
    paths = get_paths (base_path)
    overall_run_timestamp = paths['overall_run_timestamp']
    logs_dir              = paths['logs_dir']
    reports_dir           = paths['reports_dir']
    module_exec_dir       = paths['module_exec_dir']
    template_path         = paths['template_path']
    template_name         = paths['template_name']

    # get module info
    repo_basepath = 'github.com/kbaseapps'
    module_info = get_module_info (module_config_file, repo_basepath)
    module_names = module_info['module_names']
    module_repos = module_info['module_repos']

    # generate initial blank report that gets updated
    report_info = initialize_report (reports_dir, module_names, module_repos, overall_run_timestamp)
    report_file = report_info['report_file']
    report_buf  = report_info['report_buf']

    # test repos
    begdir = os.getcwd()
    for mod_i,module_name in enumerate(module_names):

        module_repo = module_repos[mod_i]
        
        # setup for subproc runs
        run_info = get_run_paths (module_names, module_repos, mod_i, module_exec_dir, logs_dir)
        clone_dir = run_info['clone_dir']
        clone_cmd = run_info['clone_cmd']
        clone_log = run_info['clone_log']
        test_dir  = run_info['test_dir']
        test_cmd  = run_info['test_cmd']
        test_log  = run_info['test_log']

        # check out repo
        stage = 'CLONE'
        chirp (stage+' '+module_name+" from "+module_repos[mod_i], prog=prog)
        clone_runbuf = run_subprocess(runcmd=clone_cmd,
                                      rundir=clone_dir,
                                      runlog=clone_log)

        # copy test_local template to module
        stage = 'COPY TEMPLATE'
        chirp (stage+' '+module_name+" from "+module_repos[mod_i], prog=prog)
        install_test_local_template (sdk_login_config_file, module_name, template_path, template_name, test_dir)

        """
        # DEBUG: replace test command with debug copy
        if module_name == 'kb_phylogenomics':
            test_script_src = os.path.join(template_path, 'kb_phylogenomics_server_test.py')
            test_script_dst = os.path.join(test_dir, 'test', 'kb_phylogenomics_server_test.py')
            print ("COPY "+test_script_src+" "+test_script_dst)
            shutil.copy(test_script_src, test_script_dst)
        """
                    
        # test module
        stage = 'UNIT TESTS'
        chirp (stage+' '+module_name+" from "+module_repos[mod_i], prog=prog)
        test_runbuf = run_subprocess(runcmd=test_cmd,
                                     rundir=test_dir,
                                     runlog=test_log,
                                     begdir=begdir,
                                     ignore_error=True)

        # read output
        stage = 'PARSE TEST LOG'
        chirp (stage+' '+module_name+" from "+module_repos[mod_i], prog=prog)
        test_scores = get_test_scores (test_runbuf)
        
        # udpate report
        stage = 'UPDATE REPORT'
        report_info = update_report (report_file, report_buf, module_name, module_repo, test_scores)
        report_file = report_info['report_file']
        report_buf  = report_info['report_buf']

    # Show report
    print ("\n\n===============================================================")
    print ("\n".join(report_buf)+"\n")
    sys.exit(0)
    
                
if __name__ == '__main__':
    main(sys.argv)
