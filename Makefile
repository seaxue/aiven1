all: 
	echo "Nothing to do."

install:
	mkdir -p /var/lib/site-prober
	cp site-prober.py /var/lib/site-prober/
	useradd prober -m -d /var/lib/site-prober
	sudo -u prober for f in configparser psycopg2 kafka-python getopt json; do pip3 install $f; done;
	cp conf/sample-consumer-service.service /etc/systemd/system/site-prober-c.service;
	cp conf/sample-producer-service.service /etc/systemd/system/site-prober-p.service;
	chmod 644 /etc/systemd/system/site-prober-*.service;

	systemctl daemon-reload;
	systemctl start site-prober-c;
	systemctl enable site-prober-c;
	systemctl start site-prober-p;
	systemctl enable site-prober-p;

clean:
	rm -f /var/lib/site-prober
	userdel -rf prober
