# RUN Jupyter notebook in a HPC cluster

You need to set three environment variables to start using this script:
- CLUSTER: whole name of the cluster use to connect via ssh (e.g., user1@cluster.hpc, cluster.hpc, etc)
- PYTHON_VENV: Path of the Python environment on the server
- WORKDIR: root directory that will be visible by Jupyter Notebook.
