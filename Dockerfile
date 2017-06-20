FROM ubuntu:14.04

RUN apt-get -y update --fix-missing
RUN apt-get -y install python python-dev python-pip

RUN pip install telepot==12.0
WORKDIR /workdir
ADD . /workdir

CMD ["/workdir/bot.sh"]
