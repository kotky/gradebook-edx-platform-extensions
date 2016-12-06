"""
This module has implementation of celery tasks for learner gradebook use cases
"""
import json
import logging

from celery.task import task  # pylint: disable=import-error,no-name-in-module

from courseware import grades
from courseware.views.views import progress_summary_wrapped
from util.request import RequestMockWithoutMiddleware
from xmodule.modulestore.django import modulestore
from xmodule.modulestore import EdxJSONEncoder
from django.db import transaction
from django.contrib.auth.models import User
from opaque_keys.edx.keys import CourseKey

from gradebook.models import StudentGradebook

log = logging.getLogger('edx.celery.task')


@task(name=u'lms.djangoapps.gradebook.tasks.update_user_gradebook')
def update_user_gradebook(course_key, user_id):
    """
    Taks to recalculate user's gradebook entry
    """
    log.info('Dosa do kraja!')
    if not isinstance(course_key, basestring):
        raise ValueError('course_key must be a string. {} is not acceptable.'.format(type(course_key)))
    course_key = CourseKey.from_string(course_key)
    try:
        user = User.objects.get(id=user_id)
        _generate_user_gradebook(course_key, user)
    except Exception as ex:
        log.exception('An error occurred while generating gradebook: %s', ex.message)
        raise
    log.info('Dosa do kraja!')


def _generate_user_gradebook(course_key, user):
    """
    Recalculates the specified user's gradebook entry
    """
    # import is local to avoid recursive import
    from courseware.courses import get_course
    course_descriptor = get_course(course_key, depth=None)
    grading_policy = course_descriptor.grading_policy
    request = RequestMockWithoutMiddleware().get('/')
    request.user = user
    request.course_descriptor = course_descriptor
    progress_summary = progress_summary_wrapped(request, course_id)
    log.info(progress_summary)
    grade_summary = grades.grade(user, course_descriptor)
    grade = grade_summary['percent']
    proforma_grade = grades.calculate_proforma_grade(grade_summary, grading_policy)

    try:
        gradebook_entry = StudentGradebook.objects.get(user=user, course_id=course_key)
        if gradebook_entry.grade != grade:
            gradebook_entry.grade = grade
            gradebook_entry.proforma_grade = proforma_grade
            gradebook_entry.progress_summary = json.dumps(progress_summary, cls=EdxJSONEncoder)
            gradebook_entry.grade_summary = json.dumps(grade_summary, cls=EdxJSONEncoder)
            gradebook_entry.grading_policy = json.dumps(grading_policy, cls=EdxJSONEncoder)
            gradebook_entry.save()
    except StudentGradebook.DoesNotExist:
        StudentGradebook.objects.create(
            user=user,
            course_id=course_key,
            grade=grade,
            proforma_grade=proforma_grade,
            progress_summary=json.dumps(progress_summary, cls=EdxJSONEncoder),
            grade_summary=json.dumps(grade_summary, cls=EdxJSONEncoder),
            grading_policy=json.dumps(grading_policy, cls=EdxJSONEncoder)
        )
