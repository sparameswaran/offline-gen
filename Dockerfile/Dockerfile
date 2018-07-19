FROM ubuntu:17.10
COPY ./ ./

 RUN apt-get update -qq \
	&& apt-get install -qqy \
			vim \
			curl \
			wget \
			git \
			jq \
			python \
			ruby-dev \
			python-pip \
			python-dev \
			libffi-dev \
			libssl-dev \
			libxml2 \
			libxml2-dev \
			libxslt1-dev \
			zlib1g-dev \
			sshpass \
			openssl \
			libssl-dev \
			libffi-dev \
			python-dev \
			build-essential 

RUN pip install --upgrade pip
RUN pip install \
			pyVim \
			pyvmomi \
			six \
			pyquery \
			xmltodict \
			ipcalc \
			click \
			Jinja2 \
			shyaml \
			dicttoxml \
			pprint \
			PyYAML \
			requests \
	&& pip install --upgrade \
					wheel \
					setuptools \
					lxml \
					enum \
					cffi \
					cryptography \
					enum34 \
					pyasn1==0.4.1


