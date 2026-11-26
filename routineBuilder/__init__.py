"""Gymmick - Build Routines (US-01), built on the team's Routine, Exercise and Student classes.

The data folder must be set first, so Routine and ActiveUser save next to the other features' files:

    from routineBuilder import buildRoutineService
    routines = buildRoutineService("data")
"""
import os

import ActiveUser
import Routine as routineModule
from accounts.repositories import UserRepository
from viewClientele.repositories import AssignedRoutineRepository

from .routineService import RoutineError, RoutineService, parseExercises, routineView


def buildRoutineService(dataDir: str) -> RoutineService:
    os.makedirs(dataDir, exist_ok=True)
    ActiveUser.setDataDir(dataDir)
    routineModule.setDataDir(dataDir)
    return RoutineService(UserRepository(dataDir), AssignedRoutineRepository(dataDir))
