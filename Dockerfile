#starts with python 3.14 environment
FROM python:3.14-slim 

#sets /app as the working dir
WORKDIR /app 

#installs uv into the containers python env
RUN pip install uv

#copies the dependency files
COPY pyproject.toml uv.lock ./

#creates a .venv file and installs prod deps there
#--frozen uses exact versions used in uv.lock and --no-dev  skips dev only deps like pytest
RUN uv sync --frozen --no-dev

#copies the rest of the project
COPY . .
 
