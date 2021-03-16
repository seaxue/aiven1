# Site Prober Structure

This is a single python file that contains both functionalities:

# No dockerization note

This is a single 300-line python program that has only 3
dependencies. It is sufficiently portable that dockerizing it would be
a waste, and it accepts no input from external users, so there would
be no security benefits, either. 

# Usage

```
python3 site-prober.py -c # This runs the consumer mode, which never returns, and inserts results into the database.
python3 site-prober.py -p # This runs the producer mode, which never returns, and which pulls its configuration from the database.
```

Initial configuration (kafka topic, database credentials, etc. are in `website-prober.ini`. 

Copy the sample `doc/config.ini.example` to `website.ini` in the root of this repository and edit it to suit your environment.

This code creates the database tables automatically, but assumes the existence of the kafka topic. (ToDo: It seems kafka topics are created automatically on first message. Check this.?)

Kafka seems to require mutual TLS, so ensure that the keys + certificates specified in your ini configuration file actually exist.

# Adding Sites to Configuration

Inject data into the following tables:

```
probe_sites # Inject urls one at a time. Take note of the site ID.
probe_regexes # Inject regexes as regex_str, and ensure that the associated_site_id matches the configured id in probe_sites
```

ToDo: Add a small script for injecting configuration automatically.

# Directory Structure

```
doc # Sample configuration file and sample systemd service files
requirements.txt, site_prober-py # Python code for the prober
website-prober.ini # The expected location of the config file.
Makefile # For installation, if you *really* wanted to. 
```

# Installation

Note: This is optional and untested. Don't do this. This program just isn't complex enough to warrant it.

# Troubleshooting

ToDo: What sorts of problems will pop up? 

## Invalid database credentials.

ToDo.

## Invalid/Missing kafka credentials/certs.

ToDo.

# Testing This Code

There are no automated tests. ToDo.

# Notes

Using 'kafka' as python module produces this error:
```
Traceback (most recent call last):
  File "/home/sea/.z0/src/aiven-assignment-1/./site-prober.py", line 197, in <module>
    from kafka.producer import KafkaProducer
  File "/home/sea/.local/lib/python3.9/site-packages/kafka/__init__.py", line 23, in <module>
    from kafka.producer import KafkaProducer
  File "/home/sea/.local/lib/python3.9/site-packages/kafka/producer/__init__.py", line 4, in <module>
    from .simple import SimpleProducer
  File "/home/sea/.local/lib/python3.9/site-packages/kafka/producer/simple.py", line 54
    return '<SimpleProducer batch=%s>' % self.async
```
..which appears to be related to this: https://github.com/dpkp/kafka-python/issues/1906

The fix is to use kafka-python as the module instead. 

