#!/usr/bin/env python3

# ========================================
# TABLE OF CONTENTS
# ========================================
#
# * STRING TABLE
# * INITIAL STATE
# * CONFIG FILE PARSING
# * GENERATE INITIAL DB TABLES
# * RETRIEVE CONFIGURATION FROM DB
# * WEBSITE PROBER - STORE RESULTS TO DB
# * WEBSITE PROBER
# * ENTRYPOINT
# 
# ========================================
# END TABLE OF CONTENTS
# ========================================

# For pulling config from the DB, as well as writing results periodically.
import psycopg2
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
# For making http requests and retrieving results/error codes
import requests
# So we can attach current timestamp to DB inserts.
import time
import sys
from os import getenv

# ==========
# STRING TABLE
# ==========

g_config_file = "website-prober.ini"

# ==========
# INITIAL STATE (UPDATED BY CONFIG FILE READ)
# ==========

# Here we store the list of urls to probe and the associated regexes as well.
# This is a list of objects of form: {id: ..., url: ..., regexes: [str1, str2, ...]}
g_probe_list = []

# A single global config class would be much neater. ToDo.
g_config_db = {}
g_config_kafka = {}

g_config_site_table = "probe_sites"
g_config_regex_table = "probe_regexes"
g_config_probe_results_table = "probe_results"
g_config_regex_probe_results_table = "regex_probe_results"

# ==========
# CONFIG FILE PARSING & INITIAL STATE SETTING
# ==========

from configparser import ConfigParser
# Reads the configuration file and sets our initial state
# The initial state may be modified again by commandline parameters. 
def read_ini_file():
    try:
        ini_parser = ConfigParser()
        ini_parser.read(g_config_file)

        for section_string in ["db", "kafka"]:
            if not ini_parser.has_section(section_string):
                # ToDo: Use format + load string into string table.
                print("error parsing config file ("+str(g_config_file)+"), expecting ["+section_string+"] section but none found.")
                return False
        
        db_configs = ini_parser.items("db")
        for expr in db_configs:
            # N.B. expr[0] is the key, expr[1] is the value. ie. key=value, key2=value2, ...
            g_config_db[expr[0]] = expr[1]

        db_configs = ini_parser.items("kafka")
        for expr in db_configs:
            g_config_kafka[expr[0]] = expr[1]

        return True

    except:
        print("Failed to read ini file.")
        pass

# ==========
# GENERATE INITIAL DB TABLES
# ==========

def generate_initial_tables(connection, cursor):
    cursor.execute("create table if not exists " + str(g_config_site_table) + " (id serial primary key, url varchar(4096))")
    # ToDo: Specify as foreign key for built-in existence checking.
    cursor.execute("create table if not exists " + str(g_config_regex_table) + " (id serial primary key, associated_site_id int, regex_str varchar(4096))")
    cursor.execute("create table if not exists " + str(g_config_probe_results_table) + " (id serial primary key, associated_site_id int, timestamp timestamp, up bool)")
    cursor.execute("create table if not exists " + str(g_config_regex_probe_results_table) + " (id serial primary key, associated_site_id int, associated_regex_id int, timestamp timestamp, found bool)")
    connection.commit()
    return True

# ==========
# RETRIEVE CONFIGURATION FROM DB
# ==========

# Pulls the list of sites to query from the db
# As well as the set of regexes to match for each.
# Updates g_probe_list.
def retrieve_site_query_config():
    global g_config_db
    global g_probe_list
    try:
        db_conn = psycopg2.connect(host=g_config_db['host'],
                                   database=g_config_db['database'],
                                   user=g_config_db['user'],
                                   port=g_config_db['port'],
                                   password=g_config_db['password'],
                                   sslmode=g_config_db['sslmode'])
        c = db_conn.cursor()

        # Generate initial tables:
        generate_initial_tables(db_conn, c)
        
        c.execute("select id, url from " + str(g_config_site_table))

        # Clear our site probe state:
        g_probe_list = []
        # Iterate over rows returned and rebuild our 'todo list' for site probing.
        row = c.fetchone()
        while row is not None:
            id = row[0]
            url = row[1]
            g_probe_list.append({'id': id, 'url': url, 'regexes': []})
            row = c.fetchone()

        # Finished, now fetch the regexes:
        for site_config in g_probe_list:
            id = site_config['id']
            c.execute("select id, regex_str from " + str(g_config_regex_table) + " where associated_site_id = " + str(id))
            # Absorb the list into our state:
            # This is done one at a time so we can safely stop if there are too many to fit in memory or if we hit some user-specified limit:
            row = c.fetchone()
            while row is not None:
                id = row[0]
                regex = row[1]
                site_config['regexes'].append((id,regex))
                row = c.fetchone()

            # Finished extracting regexes for this site.
        # Finished operating on all site configs in our state.

        # Cleanup. ToDo: Do in 'finally' block.
        c.close()
        db_conn.close()

        print("Finished reading configs, read: " + str(g_probe_list))
    except:
        # ToDo: Split into more fine-grained exceptions, one for connect, one for read, etc.
        print("Unable to load site configs from db.")
        raise
    return True

# ==========
# KAFKA CONSUMER - STORE RESULTS TO DB
# ==========

def db_store_probe_results(site_id, status_code, regex_results):
    global g_config_db
    #print("Probe result for site " + str(site_id) + " is " + str(status_code) + " ")
    #print("..with regex results: " + str(regex_results))
    try:
        db_conn = psycopg2.connect(host=g_config_db['host'],
                                   database=g_config_db['database'],
                                   user=g_config_db['user'],
                                   port=g_config_db['port'],
                                   password=g_config_db['password'],
                                   sslmode=g_config_db['sslmode'])
        cursor = db_conn.cursor()

        up_p = str(status_code)[0] == "2"
        
        # cursor.execute(...,...) should automatically escape strings to avoid injection.
        cursor.execute("insert into "+g_config_probe_results_table+" (associated_site_id, timestamp, up) values(%s, now(), %s)",
                       (str(site_id),str(up_p),))
        for regex_result_i in regex_results:
            regex_id = regex_result_i[0][0]
            regex_found_p = regex_result_i[1]
            cursor.execute("insert into "+str(g_config_regex_probe_results_table)+" (associated_site_id, associated_regex_id, timestamp, found) values(%s,%s,now(),%s)",
                           (str(site_id),str(regex_id),str(regex_found_p),))

        db_conn.commit()
        cursor.close()
        db_conn.close()
    except:
        print("Exception in store_probe_results..")
        raise

    return True

# ==========
# KAFKA CONSUMER - READ FROM TOPIC
# ==========

import json
from kafka.consumer import KafkaConsumer
def kafka_consumer_entrypoint():
    global g_config_kafka
    print("Kafka config: " + str(g_config_kafka))
    consumer = KafkaConsumer(g_config_kafka['topic_name'], g_config_kafka['group_id'],
                             bootstrap_servers=[g_config_kafka['bootstrap_server']],
                             security_protocol="SSL",
                             ssl_cafile=g_config_kafka['ssl_cafile'],
                             ssl_keyfile=g_config_kafka['ssl_keyfile'],
                             ssl_certfile=g_config_kafka['ssl_certfile'])

    for message in consumer:
        # Extract message.value:
        try:
            value = json.loads(message.value.decode('utf-8'))
            # Message is a json dictionary of form:
            # { site_id: ..., status_code: ..., regex_results: ...}
            # print(";; debug: " + str(value)) 
            db_store_probe_results(value['site_id'], value['status_code'], value['regex_results'])
        except:
            print("Unable to parse message from the kafka topic.")
            raise
    return True

# Push the results to a kafka topic, to be pulled out and stored on the other end.
# I basically copied the structure here: https://analyticshut.com/kafka-producer-and-consumer-in-python
import json
from kafka.producer import KafkaProducer
def store_probe_results(site_id, status_code, regex_results):
    global g_config_kafka
    # I'll hardcode that SSL is required. 
    producer = KafkaProducer(bootstrap_servers = [g_config_kafka['bootstrap_server']],
                             security_protocol="SSL",
                             ssl_cafile=g_config_kafka['ssl_cafile'],
                             ssl_keyfile=g_config_kafka['ssl_keyfile'],
                             ssl_certfile=g_config_kafka['ssl_certfile']
                             )
    # Since both sides of this program are trusted I can send the raw dictionary and decode it on the other end:

    message = { 'site_id': site_id, 'status_code': status_code, 'regex_results': regex_results}
    ack = producer.send(g_config_kafka['topic_name'], str(json.dumps(message)).encode('utf-8'))
    return True

# ==========
# WEBSITE PROBER
# ==========

import re
def re_found_p(regex, str):
    return re.search(regex, str) != None

# Probe one single site:
# Session is a 'requests.session' object.
# probe_config is one of the objects in the g_probe_list.
import re
def probe_site(session, probe_config):
    try:
        print("Probing site " + str(probe_config['url']))
        request_result = session.get(probe_config['url'])
        if request_result.status_code == 200:
            # Check for regexes:
            # Note that regex[0] is the id in db, regex[1] is the string
            regex_results = [(regex, re_found_p(regex[1], request_result.text)) for regex in probe_config['regexes']]
            store_probe_results(probe_config['id'], request_result.status_code, regex_results)
            return True
        else:
            # Something went wrong or we got redirected. Ignore redirects for now and log this.
            # Don't log regex results.
            store_probe_results(probe_config['id'], request_result.status_code, [])
    except:
        # Something went really wrong. Log this as a general failure. Call it an error code -1
        # ToDo: Determine if exceptions passed here are swallowed by the thread pool executor. 
        raise
    return None

# Called periodically
# Makes simultaneous requests to each site in the list and returns statistics/results.
# Operates on g_probe_list
def probe_sites():
    global g_probe_list

    # Set up multiprocessing framework:
    with ThreadPoolExecutor(max_workers = 16) as executor:
        with requests.Session() as session:
            tasks =  [executor.submit(probe_site, session, probe_config) for probe_config in g_probe_list]
            # Wait for all tasks to complete:
            for future in concurrent.futures.as_completed(tasks):
                noop = future.result() # Do nothing. The task itself stores results. Though it could also be done here.
        print("Done")
        return True

    # Never get here.
    return None

# Sleep time is in seconds.
def periodic_probe_sites(sleep_time):

    while True:
        retrieve_site_query_config()
        probe_sites()
        time.sleep(sleep_time)

    return True

# ==========
# ENTRYPOINT
# ==========
import getopt
def main(argv):

    if not read_ini_file():
        return False

    # Switch on command-line parameters:
    # Case -p: periodic probe sites (kafka producer)
    # Case -c: Insert data into DB (kafka consumer)

    opts, args = getopt.getopt(argv, "pc")
    for opt, arg in opts:
        if opt == "-p":
            # Producer mode:
            periodic_probe_sites(30)
        elif opt == "-c":
            kafka_consumer_entrypoint()

    return True

if __name__ == "__main__":
    main(sys.argv[1:])
