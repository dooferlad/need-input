'use strict';

function filter(data, filter_params)
{
    var filtered_data = {};// = angular.copy(data);
    angular.forEach(data, function(value, key){
        if (key != "issues"){
            filtered_data[key] = angular.copy(value);
        }
    });

    filtered_data["issues"] = [];
    var team = undefined;
    if(filter_params.hasOwnProperty("team")){
        angular.forEach(data["components"], function(value){
            if (value["name"] == filter_params["team"]){
                team = value["id"];
            }
        });
    }

    // Parse start and end dates from the URL search term. Invalid dates will
    // come back as NaN and will be ignored.
    var start_date = Date.parse(filter_params["start_date"]);
    var end_date = Date.parse(filter_params["end_date"]);

    angular.forEach(data["issues"], function(value){
        var include = true;

        // Filter out cards that don't match the team (component) requirement
        if (team && value["components"].indexOf(team) == -1){
            include = false;
        }

        // Filter out cards that have a completion date before the start date
        if (!isNaN(start_date)){
            if (Date.parse(value["completion_date"]) < start_date){
                include = false;
            }
        }

        // Filter out cards that have a completion date after the end date
        if (!isNaN(end_date)){
            if (Date.parse(value["completion_date"]) > end_date){
                include = false;
            }
        }

        if (filter_params["status"] &&
            value["status"] != filter_params["status"]){
            include = false;
        }

        if (include){
            filtered_data["issues"].push(value);
        }
    });

    return filtered_data;
}

function find_sprint(year, month, data) {
    for (var year_index = 0; year_index < data.sprint_data.length; year_index++) {
        for (var sprint_index = 0; sprint_index < data.sprint_data[year_index].sprints.length; sprint_index++) {

            var date = new Date(data.sprint_data[year_index].sprints[sprint_index].end);
            if (date.getFullYear() == year && date.getMonth() + 1 == month)
            {
                return data.sprint_data[year_index].sprints[sprint_index];
            }
        }
    }
}

/* Controllers */

var roadmapControllers = angular.module('roadmapControllers', []);

roadmapControllers.factory('RoadmapData', ['$http',
    function($http) {
        return $http.get('/API/ALL.json');
    }]);

roadmapControllers.controller('RoadmapListCtrl', ['$scope', 'RoadmapData', '$location',
    function($scope, RoadmapData, $location) {

        RoadmapData.success(function(data) {
            $scope.data = data[0];

            /* Add a selected tag to all sprints, which will be used for
               showing the user the selected date range. */
            /*angular.forEach(data.sprint_data, function(year){
                 angular.forEach(year.sprints, function(sprint){
                     sprint.selected = true;
                 });
            });*/

            $scope.data.first = $scope.data.sprint_data[0].sprints[0].start;
            var last_year_index = $scope.data.sprint_data.length - 1;
            var last_sprint_index = $scope.data.sprint_data[last_year_index].sprints.length - 1;
            $scope.data.last = $scope.data.sprint_data[last_year_index].sprints[last_sprint_index].end;

            var filter_params = $location.search();
            $scope.startDateString = filter_params["start_date"];
            $scope.endDateString = filter_params["end_date"];
            var start_date = Date.parse(filter_params["start_date"]);
            var end_date = Date.parse(filter_params["end_date"]);

            if(!isNaN(start_date)) {
                $scope.startDate = start_date;
            }

            if(!isNaN(end_date)) {
                $scope.endDate = end_date;
            }
        });

        $scope.isCollapsed = false;
        $scope.openSelector = "start";
        $scope.selecting = false;

        function update_range (year, end_month, save) {
            var sprint = find_sprint(year, end_month, $scope.data);
            var start = Date.parse(sprint.start);
            var end = Date.parse(sprint.end);

            if (save) {
                if ($scope.selecting == false) {
                    if (start <= $scope.startDate) {
                        $scope.openSelector = "start";
                        if (start == $scope.startDate) {
                            $scope.selecting = true;
                        }
                    } else if (end >= $scope.endDate) {
                        $scope.openSelector = "end";
                        if (end == $scope.endDate) {
                            $scope.selecting = true;
                        }
                    } else {
                        $scope.openSelector = "both";
                    }
                } else {
                    $scope.selecting = false;
                }
            }

            if ($scope.selecting == false || save == false) {
                if ($scope.openSelector == "start" || $scope.openSelector == "both") {
                    if (start >= $scope.endDate) {
                        // Really have been given end, was expecting start; switch around.
                        var old_end_date = new Date($scope.endDate);
                        var start_sprint = find_sprint(old_end_date.getFullYear(), old_end_date.getMonth() + 1, $scope.data);
                        if (save) {
                            $scope.endDate = end;
                            $scope.endDateString = sprint.end;
                        }
                        $location.search("end_date", sprint.end);

                        sprint = start_sprint;
                    }
                    if (save) {
                        $scope.startDate = start;
                        $scope.startDateString = sprint.start;
                    }
                    $location.search("start_date", sprint.start);
                }

                if ($scope.openSelector == "end" || $scope.openSelector == "both") {
                    if (end <= $scope.startDate) {
                        // Really have been given start, was expecting end; switch around.
                        var old_start_date = new Date($scope.startDate);
                        var end_sprint = find_sprint(old_start_date.getFullYear(), old_start_date.getMonth() + 1, $scope.data);
                        if (save) {
                            $scope.startDate = start;
                            $scope.startDateString = sprint.start;
                        }
                        $location.search("start_date", sprint.start);

                        sprint = end_sprint;
                    }

                    if (save) {
                        $scope.endDate = end;
                        $scope.endDateString = sprint.end;
                    }
                    $location.search("end_date", sprint.end);
                }
            }
        }

        $scope.clickSprint = function (year, end_month) {
            update_range(year, end_month, true);
        };

        $scope.mouseenterSprint = function (year, end_month) {
            if ($scope.selecting) {
                update_range(year, end_month, false);
            }
        };

        $scope.mouseleaveSprint = function () {
            var filter_params = $location.search();
            if ($scope.startDateString != filter_params["start_date"]) {
                $location.search("start_date", $scope.startDateString);
            }
            if ($scope.endDateString != filter_params["end_date"]) {
                $location.search("end_date", $scope.endDateString);
            }
        };

        $scope.sprintSelected = function (year, end_month) {
            var sprint = find_sprint(year, end_month, $scope.data);

            var filter_params = $location.search();
            var start_date = Date.parse(filter_params["start_date"]);
            var end_date = Date.parse(filter_params["end_date"]);

            if (isNaN(end_date)){
                end_date = Date.parse("9999-1-1");
            }
            if (isNaN(start_date)){
                start_date = Date.parse("1900-1-1");
            }

            return (Date.parse(sprint.start) >= start_date &&
                    Date.parse(sprint.end) <= end_date);
        };

        $scope.openSprintSelector = function(name) {
            if ($scope.isCollapsed || $scope.openSelector == name) {
                $scope.isCollapsed = !$scope.isCollapsed;
            }

            $scope.openSelector = name;
        }
    }]);

roadmapControllers.controller('RoadmapDetailCtrl',
                              ['$scope', 'RoadmapData', '$routeParams', '$window', '$location',
    function($scope, RoadmapData, $routeParams, $window, $location) {
        //$scope.team = $routeParams.team;
        var filter_params = $location.search();

        $scope.getWidth = function() {
            return $window.innerWidth;
        };
        $scope.$watch($scope.getWidth, function() {
            if (typeof $scope.done_init === 'undefined'){
                RoadmapData.success(function(data) {
                    $scope.data = filter(data[0], filter_params);
                    $scope.roadmap_data = drawRoadmap($scope.data);
                    $scope.done_init = true;
                    resizeRoadmap($scope.roadmap_data);
                });
            } else {
                resizeRoadmap($scope.roadmap_data);
            }
        });
        window.onresize = function(){
            $scope.$apply();
        }
    }]);
