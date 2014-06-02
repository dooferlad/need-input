function parse_date(d) {
    // Transform the YY-MM-DD string into a full date string for the d3 time
    // axis to use.
    var date_format = d3.time.format("%Y-%m-%d");

    if (date_format.parse(d.completion_date).getFullYear() == 9999){
        return null;
    }
    return date_format.parse(d.completion_date);
}

function get_text_position(d, x) {
    var date = parse_date(d);
    var x_pos = 25;
    if (date != null)
    {
      x_pos += x(date);
    }
    return x_pos;
}

function get_icon_points (d, width) {
    // Shapes used to draw the roadmap diagram
    var hexagon = ["-2,10", "5,0", "15,0", "22,10", "15,20", "5,20"];
    var square = ["0,0", "0,20", "20,20", "20,0"];
    var diamond = ["10,0", "20,10", "10,20", "0,10"];
    var drop = ["3,0", "17,0", "20,5", "20,7", "11,20", "9,20", "0,7", "0,5"];

    if (d.summary.substring(0, 4).toLowerCase() == "epic") {
        var arrowhead_left = (width - 15).toString();
        var arrowhead_right = (width - 3).toString();
        var epic = [
            arrowhead_left + ",-1",
            arrowhead_right + ",13",
            arrowhead_left + ",26",
            arrowhead_left + ",22",
            "0,22", "0,3",
            arrowhead_left + ",3"];
        return epic;
    }
    switch (d.status) {
        case "Drafting":
            return hexagon;
        case "Approved":
            return square;
        case "Scheduled":
            return drop;
        case "Development":
            return diamond;
        case "Closed":
            return square;
        case "Closing-out Review":
            return diamond;
        default:
            return square;
    }
}

function get_icon_transform(d, x, i) {
    var x_pos = 0;

    if (d.summary.substring(0, 4).toLowerCase() == "epic") {
        x_pos = 0;
    }
    else {
        var date = parse_date(d);
        if (date != null)
        {
            x_pos = x(date);
        }
    }

    return "translate("
        + x_pos
        + ","
        + (i * 25 + 2)
        + ")";
}

function drawRoadmap(data) {
    // Draw the roadmap diagram as an SVG.

    // Set up diagram height and y axis based on how much data there is to
    // display. vertical_padding is space for the axis to be drawn.
    // height is the height needed to display the data.
    var height = 25 * data.issues.length;
    var vertical_padding = 30;

    var y = d3.scale.linear()
        .range([height, 0])
        .domain([0, data.issues.length]);

    /*
        Setting up the SVG and getting the width right requires a bit of
        careful sequencing. We want to find the width of the element that
        we have been given to draw in and draw in that, but some browsers,
        e.g. Chrome, don't give us the width we want if we haven't started
        drawing an SVG and given it the correct height. I suspect this is
        because "clientWidth" takes into account the scroll bar and, without
        a definitive content height, Chrome plays it safe and assumes there
        will be one. To make this work:
        1. Create SVG, setting correct height
        2. Get clientWidth (scroll bar has gone at this point)
        3. Set SVG width.
     */
    var svg = d3.select(".roadmapdiagram")
        .attr("height", height + vertical_padding);
    width = d3.select(".roadmapdiagram")
        .node()
        .parentNode.clientWidth;
    svg.attr("width", width)
        .attr("height", height + vertical_padding);

    // The x scale. This is used to translate a time into an x value
    var x = d3.time.scale()
        .range([0, width]);

    // The visible x axis
    var xAxis = d3.svg.axis()
        .scale(x)
        .orient("bottom");

    // Set the minimum and maximum value
    var min_date = d3.min(data.issues,
                          function (d) { return parse_date(d); });
    var max_date = d3.max(data.issues,
                          function (d) { return parse_date(d); });
    //var scale_max = new Date(max_date.getTime() + (max_date - min_date)/4);
    x.domain([min_date, max_date]);
    //var x_max = x(scale_max);

    // Background for diagram (this can be commented out --> transparent)
    svg.append("rect")
        .attr('class', 'background')
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("fill", "#FFFFFF");

    // Attach the visible x axis. We give it a class to find it during resize
    svg.append("g")
        .attr('class', 'x axis bottom')
        .attr('transform', 'translate(0,' + height + ')')
        .call(xAxis);

    // Add an icon for each card with the card name as a label
    var icon = svg.selectAll(".icon")
        .data(data.issues)
        .enter().append("svg:a")
        .attr("xlink:href", function (d) {
                  return d.url;
              });

    tip = d3.tip()
      .attr('class', 'd3-tip')
      .offset([-10, 0])
      .html(function(d) {
        tooltip = "<ul>" +
            "<li>Key: " + d.key + "</li>";

        var i;

        for (i = 0; i < d.labels.length; i++) {
            tooltip += "<li>Label: " + d.labels[i] + "</li>"
        }

        for (i = 0; i < d.links_in.length; i++) {
            tooltip += "<li>Implements: " + d.links_in[i] + "</li>"
        }

        for (i = 0; i < d.links_out.length; i++) {
            tooltip += "<li>Depends on: " + d.links_out[i] + "</li>"
        }

        tooltip += "<li>Status: " + d.status + "</li>" +
            "</ul>";

        return tooltip;
      });

    svg.call(tip);

    // The icon is drawn as a polygon, the shape and colour of which
    // depends on the project status.
    icon.append("polygon")
        .attr("points", function (d) { return get_icon_points(d, width); })
        .attr("fill", function (d) {
                  if (parse_date(d) == null) {
                      return "grey";
                  }

                  if (d.summary.substring(0, 4).toLowerCase() == "epic") {
                      return "#ddffdd";
                  }

                  switch (d.status) {
                      case "Drafting":
                          return "yellow";
                      case "Approved":
                          return "#DCE549";
                      case "Scheduled":
                          return "#e48c48";
                      case "Development":
                          return "#00941b";
                      case "Closed":
                          return "#00a3e0";
                      case "Closing-out Review":
                          return "#008a8e";
                      default:
                          return "red";
                  }
              })
        .attr("stroke", function (d) {
                  if (parse_date(d) == null) {
                      return "grey";
                  }

                  if (d.summary.substring(0, 4).toLowerCase() == "epic") {
                      return "#aaffaa";
                  }

                  switch (d.status) {
                      case "Drafting":
                          return "#fece00";
                      case "Approved":
                          return "#e48c48";
                      case "Scheduled":
                          return "#a48c18";
                      case "Development":
                          return "#107421";
                      case "Closed":
                          return "#0060bf";
                      case "Closing-out Review":
                          return "#006b6c";
                      default:
                          return "red";
                  }
              })
        .attr("stroke-width", 2)
        .attr("transform", function (d, i) {
                      return get_icon_transform(d, x, i);
              })
        .attr("class", "roadmapicon")
        .on("mouseover", tip.show)
        .on("mouseout", tip.hide);

    icon.append("text")
        .attr("y", function (d, i) {
                  return i * 25 + 13;
              })
        .attr('x', function (d){return get_text_position(d, x)})
        .attr("dy", ".35em")
        .attr("xlink:href", function (d) {
                  return d.url;
              })
        .text(function (d) {
                  return d.summary
              })
        .attr("class", "roadmaptext");

    // We return this data to use in the resizeRoadmap function
    return {
        "svg": svg,
        "x": x,
        "xAxis": xAxis,
        "max_date": max_date,
        "min_date": min_date
    };
}

function resizeRoadmap(roadmap_data) {
    // Resize an existing roadmap diagram

    var width = d3.select(".roadmapdiagram").node().parentNode.clientWidth;

    var x = roadmap_data["x"];
    var svg = roadmap_data["svg"];
    var xAxis = roadmap_data["xAxis"];
    var max_date = roadmap_data["max_date"];
    var min_date = roadmap_data["min_date"];

    // Reset the scale the the widest it could be, we shrink it down to fit
    // the text below.
    x.range([0, width-1]);

    var max_width = 0;
    var labels = svg.selectAll('.roadmaptext')[0];

    // Run through all the labels, find the one with the right-most point and
    // resize the scale to fit it
    for(index = 0; index < labels.length; index++) {
        var node = labels[index];
        var node_width = node.getBoundingClientRect().width;

        var date = parse_date(node.__data__);
        if (date == null) {
            date = min_date;
        }

        var x_pos = x(date);
        var node_right = node_width + x_pos;

        if (node_right > max_width) {
            var new_width = width - node_width - 25;
            new_width *= x(max_date) / Math.max(x_pos, 1);
            // Make sure width never goes so small the scale logic brakes.
            new_width = Math.max(new_width, 1);

            // Reset the scale based on our calculations
            x.range([0, new_width-1]);

            // Make sure we have a comparible max_width for the next set
            // of calculations.
            max_width = x(date) + node_width;
        }
    }

    // Change the diagram size and background rectangle to match the element
    // width
    d3.select(".roadmapdiagram").attr("width", width);
    svg.selectAll('rect.background').attr('width', width);

    // Move all the icons. Note that D3 keeps the data we used
    // during the initial creation around in each element so we don't need
    // to save the metadata ourselves.
    svg.selectAll('.roadmapicon')
        .attr("transform", function (d, i) {
                  return get_icon_transform(d, x, i);
              })
        .attr("points", function (d) { return get_icon_points(d, width); });

    // Move the label text
    svg.selectAll('.roadmaptext')
        .attr('x', function (d){return get_text_position(d, x)});

    // Resize the visible axis
    svg.select('.x.axis.bottom').call(xAxis.orient('bottom'));
}
