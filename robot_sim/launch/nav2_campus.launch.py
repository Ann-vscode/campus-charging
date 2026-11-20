# R3.2 - Nav2 bring-up for the campus charging scene.
#
# Brings: map_server (maps/campus_map.yaml) + lifecycle manager,
# a static map -> odom transform (simulated odometry is drift free),
# and the stock nav2_bringup navigation_launch.py with our tuned params.
#
# Usage (Gazebo scene must already be running):
#   ros2 launch robot_sim/launch/nav2_campus.launch.py

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    this_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_dir = os.path.dirname(this_dir)
    map_yaml = os.path.join(pkg_dir, 'maps', 'campus_map.yaml')
    params_file = os.path.join(pkg_dir, 'config', 'nav2_campus_params.yaml')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    use_sim_time = LaunchConfiguration('use_sim_time')

    map_server = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[params_file, {'yaml_filename': map_yaml,
                                  'use_sim_time': use_sim_time}],
    )

    map_lifecycle = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_map',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time,
                     'autostart': True,
                     'node_names': ['map_server']}],
    )

    # simulated odometry is exact, so map -> odom is identity for R3.2
    map_to_odom = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_map_to_odom',
        output='screen',
        arguments=['--x', '0', '--y', '0', '--z', '0',
                   '--roll', '0', '--pitch', '0', '--yaw', '0',
                   '--frame-id', 'map', '--child-frame-id', 'odom'],
    )

    navigation = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(nav2_bringup_dir, 'launch', 'navigation_launch.py')),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'params_file': params_file,
            'autostart': 'true',
            'use_composition': 'False',
        }.items(),
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        map_server,
        map_lifecycle,
        map_to_odom,
        navigation,
    ])