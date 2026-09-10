// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'stream_stats.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;
/// @nodoc
mixin _$StreamStats {

 int get currentBitrateKbps; int get averageBitrateKbps; double get fps; int get droppedFrames; int get sentBytes; Duration get uptime; int get reconnectCount; double get congestionPercent;
/// Create a copy of StreamStats
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$StreamStatsCopyWith<StreamStats> get copyWith => _$StreamStatsCopyWithImpl<StreamStats>(this as StreamStats, _$identity);



@override
bool operator ==(Object other) {
  final _this = this as StreamStats;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is StreamStats&&(identical(other.currentBitrateKbps, _this.currentBitrateKbps) || other.currentBitrateKbps == _this.currentBitrateKbps)&&(identical(other.averageBitrateKbps, _this.averageBitrateKbps) || other.averageBitrateKbps == _this.averageBitrateKbps)&&(identical(other.fps, _this.fps) || other.fps == _this.fps)&&(identical(other.droppedFrames, _this.droppedFrames) || other.droppedFrames == _this.droppedFrames)&&(identical(other.sentBytes, _this.sentBytes) || other.sentBytes == _this.sentBytes)&&(identical(other.uptime, _this.uptime) || other.uptime == _this.uptime)&&(identical(other.reconnectCount, _this.reconnectCount) || other.reconnectCount == _this.reconnectCount)&&(identical(other.congestionPercent, _this.congestionPercent) || other.congestionPercent == _this.congestionPercent));
}


@override
int get hashCode {
  final _this = this as StreamStats;
  return Object.hash(runtimeType,_this.currentBitrateKbps,_this.averageBitrateKbps,_this.fps,_this.droppedFrames,_this.sentBytes,_this.uptime,_this.reconnectCount,_this.congestionPercent);
}

@override
String toString() {
  final _this = this as StreamStats;
  return 'StreamStats(currentBitrateKbps: ${_this.currentBitrateKbps}, averageBitrateKbps: ${_this.averageBitrateKbps}, fps: ${_this.fps}, droppedFrames: ${_this.droppedFrames}, sentBytes: ${_this.sentBytes}, uptime: ${_this.uptime}, reconnectCount: ${_this.reconnectCount}, congestionPercent: ${_this.congestionPercent})';
}


}

/// @nodoc
abstract mixin class $StreamStatsCopyWith<$Res>  {
  factory $StreamStatsCopyWith(StreamStats value, $Res Function(StreamStats) _then) = _$StreamStatsCopyWithImpl;
@useResult
$Res call({
 int currentBitrateKbps, int averageBitrateKbps, double fps, int droppedFrames, int sentBytes, Duration uptime, int reconnectCount, double congestionPercent
});




}
/// @nodoc
class _$StreamStatsCopyWithImpl<$Res>
    implements $StreamStatsCopyWith<$Res> {
  _$StreamStatsCopyWithImpl(this._self, this._then);

  final StreamStats _self;
  final $Res Function(StreamStats) _then;

/// Create a copy of StreamStats
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? currentBitrateKbps = null,Object? averageBitrateKbps = null,Object? fps = null,Object? droppedFrames = null,Object? sentBytes = null,Object? uptime = null,Object? reconnectCount = null,Object? congestionPercent = null,}) {
  return _then(StreamStats(
currentBitrateKbps: null == currentBitrateKbps ? _self.currentBitrateKbps : currentBitrateKbps // ignore: cast_nullable_to_non_nullable
as int,averageBitrateKbps: null == averageBitrateKbps ? _self.averageBitrateKbps : averageBitrateKbps // ignore: cast_nullable_to_non_nullable
as int,fps: null == fps ? _self.fps : fps // ignore: cast_nullable_to_non_nullable
as double,droppedFrames: null == droppedFrames ? _self.droppedFrames : droppedFrames // ignore: cast_nullable_to_non_nullable
as int,sentBytes: null == sentBytes ? _self.sentBytes : sentBytes // ignore: cast_nullable_to_non_nullable
as int,uptime: null == uptime ? _self.uptime : uptime // ignore: cast_nullable_to_non_nullable
as Duration,reconnectCount: null == reconnectCount ? _self.reconnectCount : reconnectCount // ignore: cast_nullable_to_non_nullable
as int,congestionPercent: null == congestionPercent ? _self.congestionPercent : congestionPercent // ignore: cast_nullable_to_non_nullable
as double,
  ));
}

}


/// Adds pattern-matching-related methods to [StreamStats].
extension StreamStatsPatterns on StreamStats {
/// A variant of `map` that fallback to returning `orElse`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _StreamStats value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _StreamStats() when $default != null:
return $default(_that);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// Callbacks receives the raw object, upcasted.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case final Subclass2 value:
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _StreamStats value)  $default,){
final _that = this;
switch (_that) {
case _StreamStats():
return $default(_that);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `map` that fallback to returning `null`.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case final Subclass value:
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _StreamStats value)?  $default,){
final _that = this;
switch (_that) {
case _StreamStats() when $default != null:
return $default(_that);case _:
  return null;

}
}
/// A variant of `when` that fallback to an `orElse` callback.
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return orElse();
/// }
/// ```

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( int currentBitrateKbps,  int averageBitrateKbps,  double fps,  int droppedFrames,  int sentBytes,  Duration uptime,  int reconnectCount,  double congestionPercent)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _StreamStats() when $default != null:
return $default(_that.currentBitrateKbps,_that.averageBitrateKbps,_that.fps,_that.droppedFrames,_that.sentBytes,_that.uptime,_that.reconnectCount,_that.congestionPercent);case _:
  return orElse();

}
}
/// A `switch`-like method, using callbacks.
///
/// As opposed to `map`, this offers destructuring.
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case Subclass2(:final field2):
///     return ...;
/// }
/// ```

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( int currentBitrateKbps,  int averageBitrateKbps,  double fps,  int droppedFrames,  int sentBytes,  Duration uptime,  int reconnectCount,  double congestionPercent)  $default,) {final _that = this;
switch (_that) {
case _StreamStats():
return $default(_that.currentBitrateKbps,_that.averageBitrateKbps,_that.fps,_that.droppedFrames,_that.sentBytes,_that.uptime,_that.reconnectCount,_that.congestionPercent);case _:
  throw StateError('Unexpected subclass');

}
}
/// A variant of `when` that fallback to returning `null`
///
/// It is equivalent to doing:
/// ```dart
/// switch (sealedClass) {
///   case Subclass(:final field):
///     return ...;
///   case _:
///     return null;
/// }
/// ```

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( int currentBitrateKbps,  int averageBitrateKbps,  double fps,  int droppedFrames,  int sentBytes,  Duration uptime,  int reconnectCount,  double congestionPercent)?  $default,) {final _that = this;
switch (_that) {
case _StreamStats() when $default != null:
return $default(_that.currentBitrateKbps,_that.averageBitrateKbps,_that.fps,_that.droppedFrames,_that.sentBytes,_that.uptime,_that.reconnectCount,_that.congestionPercent);case _:
  return null;

}
}

}

/// @nodoc


class _StreamStats implements StreamStats {
  const _StreamStats({required this.currentBitrateKbps, required this.averageBitrateKbps, required this.fps, required this.droppedFrames, required this.sentBytes, required this.uptime, required this.reconnectCount, required this.congestionPercent});
  

@override final  int currentBitrateKbps;
@override final  int averageBitrateKbps;
@override final  double fps;
@override final  int droppedFrames;
@override final  int sentBytes;
@override final  Duration uptime;
@override final  int reconnectCount;
@override final  double congestionPercent;

/// Create a copy of StreamStats
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$StreamStatsCopyWith<_StreamStats> get copyWith => __$StreamStatsCopyWithImpl<_StreamStats>(this, _$identity);



@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _StreamStats&&(identical(other.currentBitrateKbps, currentBitrateKbps) || other.currentBitrateKbps == currentBitrateKbps)&&(identical(other.averageBitrateKbps, averageBitrateKbps) || other.averageBitrateKbps == averageBitrateKbps)&&(identical(other.fps, fps) || other.fps == fps)&&(identical(other.droppedFrames, droppedFrames) || other.droppedFrames == droppedFrames)&&(identical(other.sentBytes, sentBytes) || other.sentBytes == sentBytes)&&(identical(other.uptime, uptime) || other.uptime == uptime)&&(identical(other.reconnectCount, reconnectCount) || other.reconnectCount == reconnectCount)&&(identical(other.congestionPercent, congestionPercent) || other.congestionPercent == congestionPercent));
}


@override
int get hashCode {
    return Object.hash(runtimeType,currentBitrateKbps,averageBitrateKbps,fps,droppedFrames,sentBytes,uptime,reconnectCount,congestionPercent);
}

@override
String toString() {
    return 'StreamStats(currentBitrateKbps: $currentBitrateKbps, averageBitrateKbps: $averageBitrateKbps, fps: $fps, droppedFrames: $droppedFrames, sentBytes: $sentBytes, uptime: $uptime, reconnectCount: $reconnectCount, congestionPercent: $congestionPercent)';
}


}

/// @nodoc
abstract mixin class _$StreamStatsCopyWith<$Res> implements $StreamStatsCopyWith<$Res> {
  factory _$StreamStatsCopyWith(_StreamStats value, $Res Function(_StreamStats) _then) = __$StreamStatsCopyWithImpl;
@override @useResult
$Res call({
 int currentBitrateKbps, int averageBitrateKbps, double fps, int droppedFrames, int sentBytes, Duration uptime, int reconnectCount, double congestionPercent
});




}
/// @nodoc
class __$StreamStatsCopyWithImpl<$Res>
    implements _$StreamStatsCopyWith<$Res> {
  __$StreamStatsCopyWithImpl(this._self, this._then);

  final _StreamStats _self;
  final $Res Function(_StreamStats) _then;

/// Create a copy of StreamStats
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? currentBitrateKbps = null,Object? averageBitrateKbps = null,Object? fps = null,Object? droppedFrames = null,Object? sentBytes = null,Object? uptime = null,Object? reconnectCount = null,Object? congestionPercent = null,}) {
  return _then(_StreamStats(
currentBitrateKbps: null == currentBitrateKbps ? _self.currentBitrateKbps : currentBitrateKbps // ignore: cast_nullable_to_non_nullable
as int,averageBitrateKbps: null == averageBitrateKbps ? _self.averageBitrateKbps : averageBitrateKbps // ignore: cast_nullable_to_non_nullable
as int,fps: null == fps ? _self.fps : fps // ignore: cast_nullable_to_non_nullable
as double,droppedFrames: null == droppedFrames ? _self.droppedFrames : droppedFrames // ignore: cast_nullable_to_non_nullable
as int,sentBytes: null == sentBytes ? _self.sentBytes : sentBytes // ignore: cast_nullable_to_non_nullable
as int,uptime: null == uptime ? _self.uptime : uptime // ignore: cast_nullable_to_non_nullable
as Duration,reconnectCount: null == reconnectCount ? _self.reconnectCount : reconnectCount // ignore: cast_nullable_to_non_nullable
as int,congestionPercent: null == congestionPercent ? _self.congestionPercent : congestionPercent // ignore: cast_nullable_to_non_nullable
as double,
  ));
}


}

// dart format on
