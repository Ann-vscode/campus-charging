# R3.1 - SIMULATION ONLY
# Launch Gazebo classic (server + client), load campus.world,
# publish the robot description, and spawn the simulated mobile robot
# at the simulated base station (7.0, 4.0, 0.1).
# NOTE: TURTLEBOT3_MODEL is forced to burger as required by the task,
#       but the robot model itself is self-contained (no TB3 meshes).

import os

os.environ['TURTLEBOT3_MODEL'] = 'burger'

# gazebo_ros computes GAZEBO_MODEL_PATH from ament packages only; on this
# machine that misses the built-in models, so model://ground_plane / sun
# trigger a hanging online lookup. Add the system model dir and disable
# the online model database to keep world loading fully local.
os.environ['GAZEBO_MODEL_PATH'] = (
    '/usr/share/gazebo-11/models' + os.pathsep +
    os.environ.get('GAZEBO_MODEL_PATH', ''))
os.environ['GAZEBO_MODEL_DATABASE_URI'] = ''

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription
from launch.actions import TimerAction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    # Paths are resolved relative to this file (机器人目录未做成 ROS package).
    this_dir = os.path.dirname(os.path.abspath(__file__))
    robot_sim_dir = os.path.dirname(this_dir)
    world_path = os.path.join(robot_sim_dir, 'worlds', 'campus.world')
    urdf_path = os.path.join(robot_sim_dir, 'urdf', 'campus_robot.urdf.xacro')
    gazebo_ros_dir = get_package_share_directory('gazebo_ros')

    gui_arg = DeclareLaunchArgument(
        'gui', default_value='true',
        description='Set false for headless simulation (no gzclient).')
    verbose_arg = DeclareLaunchArgument(
        'verbose', default_value='false',
        description='Pass verbose=true to gzserver/gzclient.')

    # --- Gazebo server: loads the campus world ---
    gazebo_server = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(gazebo_ros_dir, 'launch', 'gzserver.launch.py')),
        launch_arguments={
            'world': world_path,
            'verbose': LaunchConfiguration('verbose'),
        }.items(),
    )

    # --- Gazebo client: GUI, optional (WSLg Display=:0 available) ---
    gazebo_client = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(gazebo_ros_dir, 'launch', 'gzclient.launch.py')),
        launch_arguments={
            'verbose': LaunchConfiguration('verbose'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('gui')),
    )

    # --- robot_description via xacro -> robot_state_publisher ---
    # Quote the xacro path: this workspace lives under a directory with spaces.
    # `Command` shlex-splits the final string, so quotes keep it as one argument.
    robot_description = ParameterValue(
        Command(['xacro "', urdf_path, '"']), value_type=str)
    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
    )

    # --- spawn the SIMULATED robot at the SIMULATED base station ---
    spawn_robot = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        name='spawn_campus_robot',
        arguments=[
            '-entity', 'campus_robot',
            '-topic', 'robot_description',
            '-x', '7.0', '-y', '4.0', '-z', '0.1',
        ],
        output='screen',
    )
    # Give gzserver time to load the world and start /spawn_entity service.
    delayed_spawn = TimerAction(period=5.0, actions=[spawn_robot])

    return LaunchDescription([
        gui_arg,
        verbose_arg,
        gazebo_server,
        gazebo_client,
        robot_state_publisher,
        delayed_spawn,
    ])
