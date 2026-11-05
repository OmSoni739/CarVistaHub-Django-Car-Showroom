# Generated data migration for Phase 1 Showroom Schedule & Break Defaults

import datetime
from django.db import migrations


def initialize_showroom_schedule(apps, schema_editor):
    ShowroomSchedule = apps.get_model('bookings', 'ShowroomSchedule')
    ShowroomClosure = apps.get_model('bookings', 'ShowroomClosure')

    open_time = datetime.time(9, 0)
    close_time = datetime.time(18, 0)
    break_start = datetime.time(13, 0)
    break_end = datetime.time(14, 0)

    # Initialize operating schedules for Monday (0) through Sunday (6)
    for day in range(7):
        ShowroomSchedule.objects.get_or_create(
            day_of_week=day,
            defaults={
                'is_open': True,
                'open_time': open_time,
                'close_time': close_time,
                'slot_duration_minutes': 60,
                'is_active': True,
            }
        )

        # Initialize recurring lunch break (13:00 - 14:00) for each operating weekday
        ShowroomClosure.objects.get_or_create(
            closure_type='BREAK',
            day_of_week=day,
            defaults={
                'title': 'Daily Lunch Break',
                'start_time': break_start,
                'end_time': break_end,
                'is_recurring': True,
                'is_active': True,
            }
        )


def reverse_showroom_schedule(apps, schema_editor):
    ShowroomSchedule = apps.get_model('bookings', 'ShowroomSchedule')
    ShowroomClosure = apps.get_model('bookings', 'ShowroomClosure')

    ShowroomClosure.objects.filter(closure_type='BREAK', title='Daily Lunch Break').delete()
    ShowroomSchedule.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0002_activeslotreservation_bookingactivity_and_more'),
    ]

    operations = [
        migrations.RunPython(
            initialize_showroom_schedule,
            reverse_code=reverse_showroom_schedule
        ),
    ]

