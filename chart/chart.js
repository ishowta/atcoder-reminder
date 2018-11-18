'use strict'

// const
var canvas = document.getElementById('ratingGraph')
const OFFSET_X = 50
const OFFSET_Y = 5
const PANEL_WIDTH = canvas.width - OFFSET_X - 10
const PANEL_HEIGHT = canvas.height - OFFSET_Y - 30
const rate_step = 400
const rates = [
  [0, '#808080'],
  [400, '#804000'],
  [800, '#008000'],
  [1200, '#00C0C0'],
  [1600, '#0000FF'],
  [2000, '#C0C000'],
  [2400, '#FF8000'],
  [2800, '#FF0000']
]

// graph
var stage
var background
var chart

/*
$(window).load(() => {
  init()
})
*/

var is_first_paint = true
function paintNewChart () {
  /*
  var rating_history = [{ 'EndTime': 1476538800, 'NewRating': 103, 'Place': 181, 'ContestName': 'AtCoder Beginner Contest 046', 'StandingsUrl': '/contests/abc046/standings?watching=ishowta' }, { 'EndTime': 1477750200, 'NewRating': 802, 'Place': 259, 'ContestName': 'AtCoder Grand Contest 006', 'StandingsUrl': '/contests/agc006/standings?watching=ishowta' }, { 'EndTime': 1481377200, 'NewRating': 763, 'Place': 191, 'ContestName': 'AtCoder Beginner Contest 049', 'StandingsUrl': '/contests/abc049/standings?watching=ishowta' }, { 'EndTime': 1488031200, 'NewRating': 800, 'Place': 422, 'ContestName': 'Mujin Programming Challenge 2017', 'StandingsUrl': '/contests/mujin-pc-2017/standings?watching=ishowta' }, { 'EndTime': 1509802800, 'NewRating': 837, 'Place': 520, 'ContestName': 'AtCoder Regular Contest 084', 'StandingsUrl': '/contests/arc084/standings?watching=ishowta' }, { 'EndTime': 1511012400, 'NewRating': 852, 'Place': 615, 'ContestName': 'AtCoder Beginner Contest 079', 'StandingsUrl': '/contests/abc079/standings?watching=ishowta' }, { 'EndTime': 1527342000, 'NewRating': 833, 'Place': 831, 'ContestName': 'AtCoder Regular Contest 098', 'StandingsUrl': '/contests/arc098/standings?watching=ishowta' }, { 'EndTime': 1528638000, 'NewRating': 899, 'Place': 523, 'ContestName': 'AtCoder Beginner Contest 099', 'StandingsUrl': '/contests/abc099/standings?watching=ishowta' }, { 'EndTime': 1529156400, 'NewRating': 1023, 'Place': 313, 'ContestName': 'AtCoder Beginner Contest 100', 'StandingsUrl': '/contests/abc100/standings?watching=ishowta' }]
  const user_name = 'test'
  var date_begin = 1502372400
  var date_end = 1533724000
  const rate_min = 0
  const rate_max = 2000
  */

  var date_range = date_end - date_begin
  const rate_range = rate_max - rate_min

  // BUGFIX: Maybe createjs has insert big num bug.
  rating_history.forEach((rating) => { rating.EndTime /= 100 })

  const converter = new createjs.Matrix2D()
    .scale(PANEL_WIDTH / date_range, PANEL_HEIGHT / rate_range)
    .translate(date_range / 2, rate_range / 2)
    .scale(1, -1)
    .translate(-date_range / 2, -rate_range / 2)
    .translate(-date_begin, -rate_min)
  const scaler = new createjs.Matrix2D()
    .scale(PANEL_WIDTH / date_range, PANEL_HEIGHT / rate_range)
    .scale(1, -1)
  const c = (x, y) => converter.transformPoint(x, y)
  const cl = (x, y) => [c(x, y).x, c(x, y).y]
  const s = (x, y) => scaler.transformPoint(x, y)
  const sl = (x, y) => [s(x, y).x, s(x, y).y]

  function init () {
    stage = new createjs.Stage('ratingGraph')
    background = new createjs.Container().set({
      x: OFFSET_X,
      y: OFFSET_Y
    })
    chart = new createjs.Container().set({
      x: OFFSET_X,
      y: OFFSET_Y,
      mask: new createjs.Shape(
        new createjs.Graphics()
          .beginFill('#000')
          .drawRect(OFFSET_X, OFFSET_Y, PANEL_WIDTH, PANEL_HEIGHT)
      ),
      shadow: new createjs.Shadow('rgba(0,0,0,0.3)', 1, 2, 3)
    })
    stage.addChild(background)
    stage.addChild(chart)
    initBackground()
    stage.update()
  }

  function initBackground () {
    createjs.Shape.prototype.to = function (parent) { return parent.addChild(this) }
    createjs.Text.prototype.to = function (parent) { return parent.addChild(this) }
    // Render frame
    new createjs.Shape()
      .to(background)
      .graphics
      .beginStroke('#888')
      .setStrokeStyle(1.5)
      .drawRoundRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT, 2)

    // Render horivontal axis
    rates.forEach(([ rate, color ]) => {
      new createjs.Shape()
        .to(background)
        .set({
          alpha: 0.3,
          mask: new createjs.Shape(
            new createjs.Graphics()
              .beginFill('#000')
              .drawRect(0, 0, PANEL_WIDTH, PANEL_HEIGHT)
          )
        })
        .graphics
        .beginFill(color)
        .rect(...cl(date_begin, rate), ...sl(date_range, rate_step))

      new createjs.Shape()
        .to(background)
        .graphics
        .beginStroke('#FFF')
        .setStrokeStyle(0.5)
        .moveTo(...cl(date_begin, rate))
        .lineTo(...cl(date_end, rate))

      if (rate !== 0) {
        new createjs.Text(String(rate), '12px Lato', '#000')
          .to(background)
          .set(
            {
              x: c(date_begin, rate).x - 5,
              y: c(date_begin, rate).y,
              textAlign: 'right',
              textBaseline: 'middle'
            }
          )
      }
    })

    // Render vertical axis
    // BUGFIX: Maybe createjs has insert big num bug.
    const toDate = (str) => moment.unix(str * 100)
    const toStr = (date) => date.unix() / 100
    const nextMonth = (date) => toStr(toDate(date).add(1, 'months'))
    var month_step = date_range * 100 / (60 * 60 * 24 * 30) / (12 * 2)
    var date_current = nextMonth(date_begin)
    var date_firstmonth = date_current
    while (date_current <= date_end) {
      new createjs.Text(toDate(date_current).format('MMM'), '12px Lato', '#000')
        .to(background)
        .set(
          {
            x: c(date_current, rate_min).x,
            y: c(date_current, rate_min).y + 3,
            textAlign: 'center',
            textBaseline: 'top'
          }
        )
      if (date_current === date_firstmonth || toDate(date_current).month() === 0) {
        new createjs.Text(toDate(date_current).format('YYYY'), '12px Lato', '#000')
          .to(background)
          .set(
            {
              x: c(date_current, rate_min).x,
              y: c(date_current, rate_min).y + 18,
              textAlign: 'center',
              textBaseline: 'top'
            }
          )
      }
      new createjs.Shape()
        .to(background)
        .graphics
        .beginStroke('#FFF')
        .setStrokeStyle(0.5)
        .moveTo(...cl(date_current, rate_min))
        .lineTo(...cl(date_current, rate_max))

      for (var i = 0; i < month_step; ++i) {
        date_current = nextMonth(date_current)
      }
    }
  }

  function paintChart () {
    createjs.Shape.prototype.to = function (parent) { return parent.addChild(this) }
    createjs.Text.prototype.to = function (parent) { return parent.addChild(this) }
    // Render chart
    var line_graphics = [
      new createjs.Shape()
        .to(chart)
        .graphics
        .beginStroke('#AAA')
        .setStrokeStyle(2)
        .moveTo(...cl(rating_history[0].EndTime, rating_history[0].NewRating)),
      new createjs.Shape()
        .to(chart)
        .graphics
        .beginStroke('#FFF')
        .setStrokeStyle(0.5)
        .moveTo(...cl(rating_history[0].EndTime, rating_history[0].NewRating))
    ]
    rating_history.forEach((rating, i) => {
      new createjs.Shape()
        .to(chart)
        .set(c(rating.EndTime, rating.NewRating))
        .graphics
        .beginStroke(i === rating_history.length - 1 ? '#000' : '#FFF')
        .setStrokeStyle(0.5)
        .beginFill(rates[Math.floor(rating.NewRating / 400)][1])
        .drawCircle(0, 0, 3.5)
      line_graphics[0].lineTo(...cl(rating.EndTime, rating.NewRating))
      line_graphics[1].lineTo(...cl(rating.EndTime, rating.NewRating))
    })

    // Render name
    {
      const user_name_length = user_name.length * 7 + 4
      const frame_length = 20
      const rate = rating_history[rating_history.length - 1]
      const rate_pos = c(rate.EndTime, rate.NewRating)
      const dx = (date_begin + date_end) / 2 < rate.EndTime ? -80 : 80
      const text_pos = {
        x: rate_pos.x + dx,
        y: rate_pos.y - 16
      }

      new createjs.Shape()
        .to(chart)
        .graphics
        .beginStroke('#FFF')
        .moveTo(rate_pos.x, rate_pos.y)
        .lineTo(text_pos.x, text_pos.y)
      new createjs.Shape()
        .to(chart)
        .graphics
        .beginStroke('#888')
        .beginFill('#FFF')
        .drawRoundRect(
          text_pos.x - user_name_length / 2,
          text_pos.y - frame_length / 2,
          user_name_length,
          frame_length,
          2
        )
      new createjs.Text(user_name, '12px Lato', '#000')
        .to(chart)
        .set(
          {
            ...text_pos,
            textAlign: 'center',
            textBaseline: 'middle',
            shadow: new createjs.Shadow('', 0, 0, 0)
          }
        )
    }
  }

  if (is_first_paint) {
    init()
    is_first_paint = false
  }
  paintChart()
  stage.update()
}
