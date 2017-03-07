# -*- encoding: utf-8 -*-

import logging

from flask import Blueprint, render_template, request
import flask_login
import werkzeug.exceptions as wz_exceptions

from pillar.web.system_util import pillar_api

from flamenco.routes import flamenco_project_view
from flamenco import current_flamenco, ROLES_REQUIRED_TO_VIEW_ITEMS

blueprint = Blueprint('flamenco.jobs', __name__, url_prefix='/jobs')
perproject_blueprint = Blueprint('flamenco.jobs.perproject', __name__,
                                 url_prefix='/<project_url>/jobs')
log = logging.getLogger(__name__)

# The job statuses that can be set from the web-interface.
ALLOWED_JOB_STATUSES_FROM_WEB = {'cancel-requested', 'queued'}


@perproject_blueprint.route('/', endpoint='index')
@flamenco_project_view(extension_props=False)
def for_project(project, job_id=None, task_id=None):
    jobs = current_flamenco.job_manager.jobs_for_project(project['_id'])
    return render_template('flamenco/jobs/list_for_project.html',
                           stats={'nr_of_jobs': '∞', 'nr_of_tasks': '∞'},
                           jobs=jobs['_items'],
                           open_job_id=job_id,
                           open_task_id=task_id,
                           project=project)


@perproject_blueprint.route('/with-task/<task_id>')
@flamenco_project_view()
def for_project_with_task(project, task_id):
    from flamenco.tasks.sdk import Task

    api = pillar_api()
    task = Task.find(task_id, {'projection': {'job': 1}}, api=api)
    return for_project(project, job_id=task['job'], task_id=task_id)


@perproject_blueprint.route('/<job_id>')
@flamenco_project_view(extension_props=True)
def view_job(project, flamenco_props, job_id):
    if not request.is_xhr:
        return for_project(project, job_id=job_id)

    # Job list is public, job details are not.
    if not flask_login.current_user.has_role(*ROLES_REQUIRED_TO_VIEW_ITEMS):
        raise wz_exceptions.Forbidden()

    from .sdk import Job

    api = pillar_api()
    job = Job.find(job_id, api=api)

    from . import CANCELABLE_JOB_STATES, REQUEABLE_JOB_STATES

    write_access = current_flamenco.current_user_is_flamenco_admin()

    return render_template('flamenco/jobs/view_job_embed.html',
                           job=job,
                           project=project,
                           flamenco_props=flamenco_props.to_dict(),
                           flamenco_context=request.args.get('context'),
                           can_cancel_job=write_access and job['status'] in CANCELABLE_JOB_STATES,
                           can_requeue_job=write_access and job['status'] in REQUEABLE_JOB_STATES)


@perproject_blueprint.route('/<job_id>/depsgraph')
@flamenco_project_view(extension_props=False)
def view_job_depsgraph(project, job_id):

    # Job list is public, job details are not.
    if not flask_login.current_user.has_role(*ROLES_REQUIRED_TO_VIEW_ITEMS):
        raise wz_exceptions.Forbidden()

    if request.is_xhr:
        from flask import jsonify
        from flamenco.tasks import COLOR_FOR_TASK_STATUS

        # Return the vis.js nodes and edges as JSON
        tasks = current_flamenco.task_manager.tasks_for_job(job_id)
        nodes = []
        edges = []

        # Make a mapping from database ID to task index
        tid_to_idx = {task['_id']: tidx
                      for tidx, task in enumerate(tasks._items)}

        for task in sorted(tasks._items, key=lambda task: task['priority']):
            task_id = tid_to_idx[task['_id']]
            nodes.append({
                'id': task_id,
                'label': task['name'],
                'shape': 'box',
                'color': COLOR_FOR_TASK_STATUS[task['status']],
            })
            if task.parents:
                for parent in task.parents:
                    edges.append({
                        'from': task_id,
                        'to': tid_to_idx[parent],
                        'arrows': 'to',
                    })
        return jsonify(nodes=nodes, edges=edges)

    return render_template('flamenco/jobs/depsgraph.html',
                           job_id=job_id,
                           project=project)


@blueprint.route('/<job_id>/set-status', methods=['POST'])
def set_job_status(job_id):
    from flask_login import current_user

    new_status = request.form['status']
    if new_status not in ALLOWED_JOB_STATUSES_FROM_WEB:
        log.warning('User %s tried to set status of job %s to disallowed status "%s"; denied.',
                    current_user.objectid, job_id, new_status)
        raise wz_exceptions.UnprocessableEntity('Status "%s" not allowed' % new_status)

    log.info('User %s set status of job %s to "%s"', current_user.objectid, job_id, new_status)
    current_flamenco.job_manager.web_set_job_status(job_id, new_status)

    return '', 204


@blueprint.route('/<job_id>/redir')
def redir_job_id(job_id):
    """Redirects to the job view.

    This saves the client from performing another request to find the project URL;
    we do it for them.
    """

    from flask import redirect, url_for
    from .sdk import Job
    from pillarsdk import Project

    api = pillar_api()
    j = Job.find(job_id, {'projection': {'project': 1}}, api=api)
    p = Project.find(j.project, {'projection': {'url': 1}}, api=api)

    return redirect(url_for('flamenco.jobs.perproject.view_job',
                            project_url=p.url,
                            job_id=job_id))