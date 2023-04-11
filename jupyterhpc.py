import os
import tempfile
import subprocess
import re
import time
import webbrowser
import sys


SLURM_JOB = """#!/bin/sh
#SBATCH --job-name {0}
#SBATCH --error .{0}/{0}-%j.error
#SBATCH --output .{0}/{0}-%j.out
#SBATCH -N 1
#SBATCH --cpus-per-task 1
#SBATCH -n 1
#SBATCH --partition {1}
#SBATCH --time {2}

source {3}
ip=`hostname`
cd {4}
jupyter-notebook --no-browser --port=9700 --ip=$ip
"""


def get_var(var, default=None):

    if var in os.environ:
        return os.environ.get(var)
    elif default:
        return default

    raise RuntimeError(f"Please set {var} environment variable")


def run(cmd_list, local=False, debug=False):

    cluster = get_var('CLUSTER')
    if not local:
        cmd_list = ['ssh', cluster] + cmd_list
    process = subprocess.run(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if debug:
        print(f"Executing command: {' '.join(cmd_list)}")

    if process.returncode:
        print(process.stderr.decode().strip())

    return (
        process.returncode,
        process.stdout.decode().strip(),
        process.stderr.decode().strip(),
    )


def create_job_script():
    slurm_script = tempfile.NamedTemporaryFile("w+", prefix="jupyterhpc", delete=False)

    slurm_script.write(
        SLURM_JOB.format(
            "jupyterhpc",
            "cpu",
            "3:00:00",
            os.path.join(get_var('PYTHON_VENV'), "bin", "activate"),
            get_var('WORKDIR', "~")
        )
    )
    slurm_script.close()
    print(f"SLURM script generated: {slurm_script.name}")

    return slurm_script.name


def send_job_script(script_path):
    command = ["scp", script_path, f"{get_var('CLUSTER')}:/tmp/"]

    ret, outs, err = run(command, local=True)


def check_job_dir():
    print("Checking job directory")
    cmd_list = ["ls", ".jupyterhpc"]

    ret, outs, err = run(cmd_list)

    if ret:
        print("jupyterhpc directory does not exist")

        return False
    else:
        print("jupyterhpc configuration exist")

    return True


def launch_job(script_name):
    print("Launching job")
    cmd_list = ["sbatch", f"/tmp/{script_name}"]
    ret, outs, err = run(cmd_list)

    if not ret:
        print("Job submitted")
        job_match = re.match(r"Submitted batch job (\d+)", outs)
        if job_match:
            job_id = job_match.group(1)
            return job_id

    raise RuntimeError(outs)


def check_jobfailure(job_id):
    command = ["sacct", "-j", job_id, "-n"]
    ret, outs, err = run(command)

    if "FAILED" in outs:
        return True

    return False


def get_node(job_id):
    command = ["squeue", "-j", job_id, "-h", "--format", "%N"]
    ret, outs, err = run(command)

    if not ret:
        return outs.strip()

    raise RuntimeError(outs)


def delete_job(job_id):
    print("Deleting job")
    command = ["scancel", job_id]

    ret, outs, err = run(command)

    if not ret:
        print("Job CANCELLED")
        return

    raise RuntimeError(outs)


def get_jupyter_url(job_id):
    jupyter_dir = ".jupyterhpc"
    error_file = os.path.join(jupyter_dir, f"jupyterhpc-{job_id}.error")

    command = ["cat", error_file]
    ret, outs, err = run(command)
    if ret:
        sys.stdout.write("\rJob has not started")

    if "token" not in outs:
        return ""

    p = re.search(
        r".*(http://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,4}/\?token=\w+).*", outs
    )
    if not p:
        return ""

    url = p.group(1)

    return url


def main():
    script_path = create_job_script()
    send_job_script(script_path)
    script_name = os.path.basename(script_path)
    job_id = launch_job(script_name)
    print(f"Got job id {job_id}")

    url = None
    count = 0
    while not url:
        time.sleep(0.5)
        sys.stdout.write("\r+ Waiting URL ...   ")
        sys.stdout.flush()
        count += 1
        if count % 2 == 0:
            sys.stdout.write("\r.")

        url = get_jupyter_url(job_id)
        if check_jobfailure(job_id):
            jupyter_dir = ".jupyterhpc"
            error_file = os.path.join(jupyter_dir, f"jupyterhpc-{job_id}.error")
            print(f"Job {job_id} failed please have a look at: ~/{error_file}")
            exit(1)

    data = re.match(
        r"^http://(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{2,4})/\?token=(\w+)$", url
    )
    if data:
        ip = data.group(1)
        port = data.group(2)
        token = data.group(3)

    ip = get_node(job_id)

    print(f"Opening SSH tunel on node {ip} and port {port}")
    print(f"Jupyter token: {token}")

    cmd = ["ssh", "-N", get_var('CLUSTER'), "-L", f"8080:{ip}:{port}"]

    ssh_t = subprocess.Popen(cmd)

    webbrowser.open(f"http://127.0.0.1:8080/?token={token}")

    try:
        ssh_t.wait()

    except KeyboardInterrupt:

        delete_job(job_id)


if __name__ == "__main__":
    main()
