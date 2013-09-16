import socket
import urllib
import time

from flask import Flask, render_template, jsonify, redirect, url_for, request
from model import *
from jobs import *
from workers import *
from shots import *

app = Flask(__name__)
app.config.update(
	DEBUG=True,
	SERVER_NAME='brender-server:9999'
)

@app.route('/')
def index():
	return jsonify(status = 'ok')


@app.route('/workers/')
def workers():
    workers = {}

    for worker in Workers.select():
        try:
            f = urllib.urlopen('http://' + worker.ip_address)
            worker.connection = 'online'
        except Exception, e:
            print '[Warning] Worker', worker.hostname, 'is not online'
            worker.connection = 'offline'

        workers[worker.hostname] = {
            "id": worker.id,
            "hostname" : worker.hostname,
            "status" : worker.status,
            "connection" : worker.connection,
            "ip_address" : worker.ip_address}

    """
    This is a temporary solution for saving the workers connections: 
    we read them from the workers dict we just created and build an 
    update query for each one of them. It seems not possible to save
    the objects on the fly in the Workers.select() loop above.
    """
    
    for k, v in workers.iteritems():
        update_query = Workers.update(connection=v['connection']).where(Workers.id == v['id'])
        update_query.execute()

    return jsonify(workers)

@app.route('/workers/edit', methods=['POST'])
def workers_edit():
    worker_ids = request.form['id']
    worker_data = {
        "status" : request.form['status'],
        "config" : request.form['config']
    }

    if worker_ids:
        for worker_id in list_integers_string(worker_ids):
            worker = Workers.get(Workers.id == worker_id)
            update_worker(worker, worker_data)

        return jsonify(result = 'success')
    else:
        print 'we edit all the workers'
        for worker in Workers.select():
            update_worker(worker, worker_data)

    return jsonify(result = 'success')

@app.route('/workers/run_command')
def worker_run_command():
    print "server run command point"
    #command = request.form['command']
    #arguments = request.form['arguments']
    ip_address = '127.0.0.1:5000'
    
    return http_request(ip_address, '/run_command')
    #return "test"
    #return jsonify(result = 'success')


@app.route('/shots/')
def shots():
    shots = {}
    for shot in Shots.select():
        if shot.frame_start == shot.current_frame:
            percentage_done = 0
        else:
            frame_count = shot.frame_end - shot.frame_start + 1
            current_frame = shot.current_frame - shot.frame_start + 1
            percentage_done = 100 / frame_count * current_frame

        shots[shot.id] = {
            "frame_start" : shot.frame_start,
            "frame_end" : shot.frame_end,
            "current_frame" : shot.current_frame,
            "status" : shot.status,
            "shot_name" : shot.shot_name,
            "percentage_done" : percentage_done,
            "render_settings" : shot.render_settings}
    return jsonify(shots)

@app.route('/shots/start/<int:shot_id>')
def shot_start(shot_id):
    try:
        shot = Shots.get(Shots.id == shot_id)
    except Exception, e:
        print e , '--> Shot not found'
        return 'Shot %d not found' %shot_id

    if shot.status == 'started':
        return 'Shot already started'
    else:
        shot.status = 'started'
        shot.save()
        #http_request()
        return 'Shot started'

@app.route('/shots/add', methods=['POST'])
def shot_add():
    print 'adding shot'

    shot = Shots.create(
        production_shot_id = 1,
        frame_start = int(request.form['frame_start']),
        frame_end = int(request.form['frame_end']),
        chunk_size = int(request.form['chunk_size']),
        current_frame = int(request.form['frame_start']),
        filepath = request.form['filepath'],
        shot_name = request.form['shot_name'],
        render_settings = 'will refer to settings table',
        status = 'running',
        priority = 10,
        owner = 'fsiddi')

    print 'parsing shot to create jobs'

    create_jobs(shot)

    print 'refresh list of available workers'

    dispatch_jobs()

    return 'done'

@app.route('/shots/delete', methods=['POST'])
def shots_delete():
    shot_ids = request.form['id']
    shots_list =list_integers_string(shot_ids)
    for shot_id in shots_list:
        print 'working on', shot_id, '-', str(type(shot_id))
        # first we delete the associated jobs (no foreign keys)
        delete_jobs(shot_id)
        # then we delete the shot
        delete_shot(shot_id)        
    return 'done'

@app.route('/jobs/')
def jobs():
    jobs = {}
    for job in Jobs.select():

        if job.chunk_start == job.current_frame:
            percentage_done = 0
        else:
            frame_count = job.chunk_end - job.chunk_start + 1
            current_frame = job.current_frame - job.chunk_start + 1
            percentage_done = 100 / frame_count * current_frame

        jobs[job.id] = {
            "shot_id" : job.shot_id,
            "chunk_start" : job.chunk_start,
            "chunk_end" : job.chunk_end,
            "current_frame" : job.current_frame,
            "status" : job.status,
            "percentage_done" : percentage_done,
            "priority" : job.priority}
    return jsonify(jobs)


@app.route('/connect', methods=['POST', 'GET'])
def connect():
    error = None
    if request.method == 'POST':
        #return str(request.json['foo'])
        
        #ip_address = request.form['ip_address']
        ip_address = '127.0.0.1:5000'
        mac_address = request.form['mac_address']
        hostname = request.form['hostname']

        try:
            worker = Workers.get(Workers.mac_address == mac_address)
        except Exception, e:
            print e , '--> Worker not found'
            worker = False

        if worker:
            print('This worker connected before, updating IP address')
            worker.ip_address = ip_address
            worker.save()

        else:
            print('This worker never connected before')
            # create new worker object with some defaults. Later on most of these
            # values will be passed as JSON object during the first connection
            
            worker = Workers.create(
                hostname = hostname, 
                mac_address = mac_address, 
                status = 'enabled',
                connection = 'online', 
                warning = False, 
                config = 'bla',
                ip_address = ip_address)
            
            print('Worker has been added')

        #params = urllib.urlencode({'worker': 1, 'eggs': 2})
        
        # we verify the identity of the worker (will check on database)
        f = urllib.urlopen('http://' + ip_address)
        print 'The following worker just connected:'
        print f.read()
        
        return 'You are now connected to the server'
    # the code below is executed if the request method
    # was GET or the credentials were invalid
    return jsonify(error = error)

if __name__ == "__main__":
    app.run()