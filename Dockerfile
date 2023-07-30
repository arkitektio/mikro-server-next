FROM python:3.10

# Install dependencies
RUN pip install poetry rich
RUN poetry config virtualenvs.create false 
ENV PYTHONUNBUFFERED=1


RUN mkdir /workspaces