# pylint: disable=E1101
"""
Run these tests @ Devstack:
    paver test_system -s lms --test_id=lms/djangoapps/gradebook/tests.py
"""
from mock import MagicMock, patch
import uuid
import json

from collections import OrderedDict
from datetime import datetime
from django.utils.timezone import UTC

from django.conf import settings
from django.test.utils import override_settings

from capa.tests.response_xml_factory import StringResponseXMLFactory
from courseware import module_render
from courseware.model_data import FieldDataCache
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase, mixed_store_config
from student.tests.factories import UserFactory, AdminFactory
from courseware.tests.factories import StaffFactory
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory

from gradebook.models import StudentGradebook, StudentGradebookHistory
from util.signals import course_deleted


MODULESTORE_CONFIG = mixed_store_config(settings.COMMON_TEST_DATA_ROOT, {}, include_xml=False)


@override_settings(MODULESTORE=MODULESTORE_CONFIG)
@override_settings(STUDENT_GRADEBOOK=True)
class GradebookTests(ModuleStoreTestCase):
    """ Test suite for Student Gradebook """

    def get_module_for_user(self, user, course, problem):
        """Helper function to get useful module at self.location in self.course_id for user"""
        mock_request = MagicMock()
        mock_request.user = user
        field_data_cache = FieldDataCache.cache_for_descriptor_descendents(
            course.id, user, course, depth=2)

        return module_render.get_module(  # pylint: disable=protected-access
            user,
            mock_request,
            problem.location,
            field_data_cache,
        )._xmodule

    def setUp(self):
        super(GradebookTests, self).setUp()
        self.test_server_prefix = 'https://testserver'
        self.user = UserFactory()
        self.score = 0.75

    # pylint: disable=attribute-defined-outside-init
    def _create_course(self, start=None, end=None):
        self.course = CourseFactory.create(
            start=start,
            end=end
        )
        self.course.always_recalculate_grades = True
        test_data = '<html>{}</html>'.format(str(uuid.uuid4()))
        chapter1 = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=test_data,
            display_name="Chapter 1"
        )
        chapter2 = ItemFactory.create(
            category="chapter",
            parent_location=self.course.location,
            data=test_data,
            display_name="Chapter 2"
        )
        ItemFactory.create(
            category="sequential",
            parent_location=chapter1.location,
            data=test_data,
            display_name="Sequence 1",
        )
        ItemFactory.create(
            category="sequential",
            parent_location=chapter2.location,
            data=test_data,
            display_name="Sequence 2",
        )
        ItemFactory.create(
            parent_location=chapter2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='foo'),
            metadata={'rerandomize': 'always'},
            display_name="test problem 1",
            max_grade=45
        )
        self.problem = ItemFactory.create(
            parent_location=chapter1.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="homework problem 1",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Homework"}
        )
        self.problem_progress_summary = {
            "url_name": "homework_problem_1",
            "display_name": "homework problem 1",
            "graded": True,
            "format": "Homework",
            "section_total": [0.75, 1.0, False, "homework problem 1", None, None],
            "due": None,
            "scores": [[0.75, 1.0, True, "homework problem 1", unicode(self.problem.location), None]]
        }
        self.problem_grade_summary = {
            "category": "Homework",
            "percent": 0.75,
            "detail": "Homework 1 - homework problem 1 - 75% (0.75/1)",
            "label": "HW 01"
        }
        self.problem2 = ItemFactory.create(
            parent_location=chapter2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="homework problem 2",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Homework"}
        )
        self.problem2_progress_summary = {
            "url_name": "homework_problem_2",
            "display_name": "homework problem 2",
            "graded": True,
            "format": "Homework",
            "section_total": [0.95, 1.0, False, "homework problem 2", None, None],
            "due": None,
            "scores": [[0.95, 1.0, True, "homework problem 2", unicode(self.problem2.location), None]]
        }
        self.problem2_grade_summary = {
            "category": "Homework",
            "percent": 0.95,
            "detail": "Homework 2 - homework problem 2 - 95% (0.95/1)",
            "label": "HW 02"
        }
        self.problem3 = ItemFactory.create(
            parent_location=chapter2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="lab problem 1",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Lab"}
        )
        self.problem3_progress_summary = {
            "url_name": "lab_problem_1",
            "display_name": "lab problem 1",
            "graded": True,
            "format": "Lab",
            "section_total": [0.86, 1.0, False, "lab problem 1", None, None],
            "due": None,
            "scores": [[0.86, 1.0, True, "lab problem 1", unicode(self.problem3.location), None]]
        }
        self.problem3_grade_summary = {
            "category": "Lab",
            "percent": 0.86,
            "detail": "Lab 1 - lab problem 1 - 86% (0.86/1)",
            "label": "Lab 01"
        }
        self.problem4 = ItemFactory.create(
            parent_location=chapter2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="midterm problem 2",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Midterm Exam"}
        )
        self.problem4_progress_summary = {
            "url_name": "midterm_problem_2",
            "display_name": "midterm problem 2",
            "graded": True,
            "format": "Midterm Exam",
            "section_total": [0.92, 1.0, False, "midterm problem 2", None, None],
            "due": None,
            "scores": [[0.92, 1.0, True, "midterm problem 2", unicode(self.problem4.location), None]]
        }
        self.problem4_grade_summary = OrderedDict([
            ("category", "Midterm Exam"),
            ("prominent", True),
            ("percent", 0.92),
            ("detail", "Midterm Exam = 92%"),
            ("label", "Midterm")
        ])
        self.problem5 = ItemFactory.create(
            parent_location=chapter2.location,
            category='problem',
            data=StringResponseXMLFactory().build_xml(answer='bar'),
            display_name="final problem 2",
            metadata={'rerandomize': 'always', 'graded': True, 'format': "Final Exam"}
        )
        self.problem5_progress_summary = {
            "url_name": "final_problem_2",
            "display_name": "final problem 2",
            "graded": True,
            "format": "Final Exam",
            "section_total": [0.87, 1.0, False, "final problem 2", None, None],
            "due": None,
            "scores": [[0.87, 1.0, True, "final problem 2", unicode(self.problem5.location), None]]
        }
        self.problem5_grade_summary = OrderedDict([
            ("category", "Final Exam"),
            ("prominent", True),
            ("percent", 0.87),
            ("detail", "Final Exam = 87%"),
            ("label", "Final")
        ])
        self.grading_policy = {
            "GRADER": [{
                "short_label": "HW",
                "min_count": 12,
                "type": "Homework",
                "drop_count": 2,
                "weight": 0.15
            }, {
                "min_count": 12,
                "type": "Lab",
                "drop_count": 2,
                "weight": 0.15
            }, {
                "short_label": "Midterm",
                "min_count": 1,
                "type": "Midterm Exam",
                "drop_count": 0,
                "weight": 0.3
            }, {
                "short_label": "Final",
                "min_count": 1,
                "type": "Final Exam",
                "drop_count": 0,
                "weight": 0.4
            }],
            "GRADE_CUTOFFS": {"Pass": 0.5}
        }

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True
    })
    def test_receiver_on_score_changed(self):
        self._create_course()
        module = self.get_module_for_user(self.user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.01)
        self.assertEqual(gradebook.proforma_grade, 0.75)
        self.assertIn(json.dumps(self.problem_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        module = self.get_module_for_user(self.user, self.course, self.problem2)
        grade_dict = {'value': 0.95, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.03)
        self.assertEqual(gradebook.proforma_grade, 0.8500000000000001)
        self.assertIn(json.dumps(self.problem2_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem2_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        module = self.get_module_for_user(self.user, self.course, self.problem3)
        grade_dict = {'value': 0.86, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.04)
        self.assertEqual(gradebook.proforma_grade, 0.855)
        self.assertIn(json.dumps(self.problem3_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem3_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        module = self.get_module_for_user(self.user, self.course, self.problem4)
        grade_dict = {'value': 0.92, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.31)
        self.assertEqual(gradebook.proforma_grade, 0.8831666666666667)
        self.assertIn(json.dumps(self.problem4_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem4_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        module = self.get_module_for_user(self.user, self.course, self.problem5)
        grade_dict = {'value': 0.87, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.66)
        self.assertEqual(gradebook.proforma_grade, 0.8805000000000001)
        self.assertIn(json.dumps(self.problem5_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem5_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 1)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 5)

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True,
        'ENABLE_NOTIFICATIONS': True
    })

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True
    })
    def test_open_course(self):
        self._create_course(start=datetime(2010, 1, 1, tzinfo=UTC()), end=datetime(3000, 1, 1, tzinfo=UTC()))

        module = self.get_module_for_user(self.user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.01)
        self.assertEqual(gradebook.proforma_grade, 0.75)
        self.assertIn(json.dumps(self.problem_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        module = self.get_module_for_user(self.user, self.course, self.problem2)
        grade_dict = {'value': 0.95, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.03)
        self.assertEqual(gradebook.proforma_grade, 0.8500000000000001)
        self.assertIn(json.dumps(self.problem2_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem2_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 1)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 2)

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True
    })
    def test_not_yet_started_course(self):
        self._create_course(start=datetime(3000, 1, 1, tzinfo=UTC()), end=datetime(3000, 1, 1, tzinfo=UTC()))

        module = self.get_module_for_user(self.user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.01)
        self.assertEqual(gradebook.proforma_grade, 0.75)
        self.assertIn(json.dumps(self.problem_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        module = self.get_module_for_user(self.user, self.course, self.problem2)
        grade_dict = {'value': 0.95, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.03)
        self.assertEqual(gradebook.proforma_grade, 0.8500000000000001)
        self.assertIn(json.dumps(self.problem2_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem2_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 1)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 2)

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True
    })
    def test_closed_course_student(self):
        self._create_course(start=datetime(2010, 1, 1, tzinfo=UTC()), end=datetime(2011, 1, 1, tzinfo=UTC()))

        module = self.get_module_for_user(self.user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        with self.assertRaises(StudentGradebook.DoesNotExist):
            gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)

        module = self.get_module_for_user(self.user, self.course, self.problem2)
        grade_dict = {'value': 0.95, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        with self.assertRaises(StudentGradebook.DoesNotExist):
            gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 0)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 0)

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True
    })
    def test_closed_course_admin(self):
        """
        Users marked as Admin should be able to submit grade events to a closed course
        """
        self.user = AdminFactory()
        self._create_course(start=datetime(2010, 1, 1, tzinfo=UTC()), end=datetime(2011, 1, 1, tzinfo=UTC()))

        module = self.get_module_for_user(self.user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        with self.assertRaises(StudentGradebook.DoesNotExist):
            gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)

        module = self.get_module_for_user(self.user, self.course, self.problem2)
        grade_dict = {'value': 0.95, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        with self.assertRaises(StudentGradebook.DoesNotExist):
            gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 0)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 0)

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True
    })
    def test_closed_course_staff(self):
        """
        Users marked as course staff should be able to submit grade events to a closed course
        """
        self._create_course(start=datetime(2010, 1, 1, tzinfo=UTC()), end=datetime(2011, 1, 1, tzinfo=UTC()))
        self.user = StaffFactory(course_key=self.course.id)

        module = self.get_module_for_user(self.user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        with self.assertRaises(StudentGradebook.DoesNotExist):
            gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)

        module = self.get_module_for_user(self.user, self.course, self.problem2)
        grade_dict = {'value': 0.95, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        with self.assertRaises(StudentGradebook.DoesNotExist):
            gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 0)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 0)

    def test_update_user_gradebook_task_arguments(self):
        """
        Tests update_user_gradebook task is called with appropriate arguments
        """
        self._create_course()
        user = UserFactory()
        module = self.get_module_for_user(user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': user.id}
        with patch('gradebook.signals.update_user_gradebook.delay') as mock_task:
            module.system.publish(module, 'grade', grade_dict)
            mock_task.assert_called_with(unicode(self.course.id), user.id)

    @patch.dict(settings.FEATURES, {
        'ALLOW_STUDENT_STATE_UPDATES_ON_CLOSED_COURSE': False,
        'SIGNAL_ON_SCORE_CHANGED': True
    })
    def test_receiver_on_course_deleted(self):
        self._create_course(start=datetime(2010, 1, 1, tzinfo=UTC()), end=datetime(2020, 1, 1, tzinfo=UTC()))
        module = self.get_module_for_user(self.user, self.course, self.problem)
        grade_dict = {'value': 0.75, 'max_value': 1, 'user_id': self.user.id}
        module.system.publish(module, 'grade', grade_dict)

        gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)
        self.assertEqual(gradebook.grade, 0.01)
        self.assertEqual(gradebook.proforma_grade, 0.75)
        self.assertIn(json.dumps(self.problem_progress_summary), gradebook.progress_summary)
        self.assertIn(json.dumps(self.problem_grade_summary), gradebook.grade_summary)
        self.assertEquals(json.loads(gradebook.grading_policy), self.grading_policy)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 1)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 1)

        course_deleted.send(sender=None, course_key=self.course.id)

        with self.assertRaises(StudentGradebook.DoesNotExist):
            gradebook = StudentGradebook.objects.get(user=self.user, course_id=self.course.id)

        gradebook = StudentGradebook.objects.all()
        self.assertEqual(len(gradebook), 0)

        history = StudentGradebookHistory.objects.all()
        self.assertEqual(len(history), 0)
