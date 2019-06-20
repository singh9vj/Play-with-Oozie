import os
import json
import sys
import subprocess
import requests
from collections import defaultdict

build_result = "build.json"
hdfs_back_dir = os.environ['HDFS_BACK_DIR']

def execute_command(command):
    print(command)
    process = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
    output = process.communicate()[0].strip()
    return (output, process.returncode)

def get_details_of_build_process(build_result):
    with open(build_result) as json_file:
        data = json.load(json_file)
    return data

def get_backup_directory_info(data):
    print("[INFO] Taking backup first..")
    output = defaultdict(dict)
    for key , value in data.iteritems():
        app_name = os.path.dirname(key)
        app_name = os.path.basename(app_name)
        tmp_list = []
        print("[INFO] Found cordinator for this application %s" %(app_name))
        for k,v in value.iteritems():
            if app_name in output:
                tmp_list.append(k)
                tmp_list = list(set(tmp_list))
                output[app_name] = tmp_list
            else:
                tmp_list.append(k)
                tmp_list = list(set(tmp_list))
                output[app_name] = tmp_list
    print(output)
    return output

def create_subworkflow_dir(appname, workflow_info):
    create_hdfs_directory_command = "hdfs dfs -mkdir " + appname
    create_output, create_status_code = execute_command(create_hdfs_directory_command)
    if create_status_code == 0:
        for each_element in workflow_info:
            sub_dir = appname + "/" + str(each_element)
            command = "hdfs dfs -mkdir " + sub_dir
            execute_command(command)
    else:
        print("ERROR in creating backup directory in hdfs")
        sys.exit(1)

def check_backup_directory(directory_info, hdfs_back_dir):
    print("[INFO] Going to check backup folder")
    for key, value in directory_info.iteritems():
        app_name = os.path.dirname(key)
        app_name = os.path.basename(app_name)
        application_dir = hdfs_back_dir + "/" + str(app_name)
        hdfs_command = "if hdfs dfs -test -d " + application_dir + "; then echo 'exist'; fi"
        output, status = execute_command(hdfs_command)
        if output == "exist" and status == 0:
            print("[INFO] Backup directory of this application: %s already exist so recreating from fresh.." %(str(key)))
            remove_backup_command = "hdfs dfs -rm -r " + application_dir
            remove_output, remove_status = execute_command(remove_backup_command)
            if remove_status == 0:
                create_subworkflow_dir(application_dir, value)
        else:
            print("[INFO] Backup directory of this application: %s does not exist previously so going to create.." %(str(key)))
            create_subworkflow_dir(application_dir, value)


def take_backup_from_hdfs_and_vice_versa(build_info, hdfs_back_dir, type):
    application_name = None
    workflow_name = None
    for key , value in build_info.iteritems():
        app_name = os.path.dirname(key)
        app_name = os.path.basename(app_name)
        application_name = str(app_name)
        for k,v in value.iteritems():
            workflow_name = str(k)
            workflow_backup_dir = hdfs_back_dir + "/" + application_name + "/" + workflow_name + "/"
            workflow_hdfs_path = str(v["hdfs_path"])
            if type == "release":
                backup_copy_command = "hdfs dfs -mv" + " " + workflow_hdfs_path + " " + workflow_backup_dir
                print("[INFO] Taking backup of this application: %s of this component: %s from hdfs path: %s to back up directory: %s" %(application_name, workflow_name, workflow_hdfs_path, workflow_backup_dir))
                backup_output , backup_result = execute_command(backup_copy_command)
                if backup_result == 0:
                    print("[INFO] Backup finished for this workflow")
                else:
                    print("[ERROR] Something happened while executing this command %s" %(backup_copy_command))
                    exit(1)
            elif type == "revert":
                print("[INFO] Revert process started for this application: %s for this workflow: %s " %(application_name, workflow_name))
                get_file_name_command = "hdfs dfs -ls " + workflow_backup_dir
                get_filename, get_file_name_status_code =  execute_command(get_file_name_command)
                revert_command = "hdfs dfs -mv" + " " + workflow_backup_dir + get_filename + " " + workflow_hdfs_path
                revert_output, revert_status_code = execute_command(revert_command)
                if revert_status_code == 0:
                    print("[INFO] Revert process finished for this application: %s for this workflow: %s " %(application_name, workflow_name))
                else:
                    print("[ERROR] Something bad happened while trying to revert this application: %s for this workflow: %s " %(application_name, workflow_name))
            else:
                continue

def download_artifact_from_nexus(nexus_url, path_to_download):
    successfully_download = False
    filename = nexus_url[nexus_url.rfind("/")+1:]
    full_path = path_to_download + "/" + filename
    if os.path.isfile(filename):
        os.remove(filename)
    else:
        with open(full_path, "wb") as file:
            response = requests.get(nexus_url)
            file.write(response.content)
        if response.status_code == 200:
            successfully_download = True
        else:
            successfully_download = False
    return (full_path, successfully_download)

def copy_from_local_to_hdfs(build_data):
    output = defaultdict(dict)
    for key , value in build_data.iteritems():
        app_name = os.path.dirname(key)
        app_name = str(os.path.basename(app_name))
        print("[INFO] Going to do deployment of this application %s" %(app_name))
        for k,v in value.iteritems():
            if str(k) == "GAVR":
                download_path = "/tmp"
                output_path , able_to_download = download_artifact_from_nexus(str(v["source_path"]), download_path)
                source_path = output_path
            else:
                source_path = str(v["source_path"])
            if k in output:
                if str(v["hdfs_path"]) == str(output[k]):
                    print("[INFO] This artifact: %s has allready been copied" %(source_path))
                    continue
                else:
                    continue
            else:
                output[k] = v["hdfs_path"]
                hdfs_path = str(v["hdfs_path"])
                deployment_command = "hdfs dfs -copyFromLocal " + source_path + " " + hdfs_path
                deployment_output, deployment_status_code = execute_command(deployment_command)
                if deployment_status_code == 0:
                    print("[INFO] Successfully copied from local: %s to hdfs path: %s" %(source_path, hdfs_path))
                else:
                    print("[ERROR] Something went wrong while copying from local: %s to hdfs path: %s" %(source_path, hdfs_path))
                    print("[ERROR] Going to revert the changes")
                    sys.exit(1)
        print("[INFO] Successfully copied all the artifact now loading this cordinator: %s" %(str(key)))
        hue_command = "/opt/cloudera/parcels/CDH/lib/hue/build/env/bin/hue loaddata " + str(key)
        hue_command_output, hue_command_status_code = execute_command(hue_command)
        if hue_command_status_code == 0:
            print("[INFO] Successfully imported the cordinator")
        else:
            print("[ERROR] Something went wrong while executing this command: %s" %(hue_command))
            sys.exit(1)
    print("[INFO] Deployment done successfully..")

def main():
    do_what =  sys.argv[1]
    if do_what == "release":
        print("[INFO] Going to do deployment")
        print("[INFO] Getting all details required for deployment")
        details = get_details_of_build_process(build_result)
        backup_directory_info = get_backup_directory_info(details)
        check_backup_directory(details, hdfs_back_dir)
        take_backup_from_hdfs_and_vice_versa(details, hdfs_back_dir, "release")
        copy_from_local_to_hdfs(details)
    elif do_what == "revert":
        print("[INFO] Going to revert back")
        details = get_details_of_build_process(build_result)
        take_backup_from_hdfs_and_vice_versa(details, hdfs_back_dir, "revert")

    else:
        print("[ERROR] This service : %s is not currently supported" %(do_what))

if __name__ == '__main__':
    main()