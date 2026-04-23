from .orbit import OrbitScreen
from .crew import CrewScreen
from .docking import DockingScreen
from .weather import WeatherScreen
from .events import EventsScreen
from .passes import PassesScreen

SCREENS = [
    OrbitScreen(),
    CrewScreen(),
    DockingScreen(),
    WeatherScreen(),
    EventsScreen(),
    PassesScreen(),
]
