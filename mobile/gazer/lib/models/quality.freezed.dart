// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'quality.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$QualitySettings {

 Resolution get resolution; FrameRate get frameRate; int get videoBitrateKbps; bool get adaptiveBitrate;
/// Create a copy of QualitySettings
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$QualitySettingsCopyWith<QualitySettings> get copyWith => _$QualitySettingsCopyWithImpl<QualitySettings>(this as QualitySettings, _$identity);

  /// Serializes this QualitySettings to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as QualitySettings;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is QualitySettings&&(identical(other.resolution, _this.resolution) || other.resolution == _this.resolution)&&(identical(other.frameRate, _this.frameRate) || other.frameRate == _this.frameRate)&&(identical(other.videoBitrateKbps, _this.videoBitrateKbps) || other.videoBitrateKbps == _this.videoBitrateKbps)&&(identical(other.adaptiveBitrate, _this.adaptiveBitrate) || other.adaptiveBitrate == _this.adaptiveBitrate));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as QualitySettings;
  return Object.hash(runtimeType,_this.resolution,_this.frameRate,_this.videoBitrateKbps,_this.adaptiveBitrate);
}

@override
String toString() {
  final _this = this as QualitySettings;
  return 'QualitySettings(resolution: ${_this.resolution}, frameRate: ${_this.frameRate}, videoBitrateKbps: ${_this.videoBitrateKbps}, adaptiveBitrate: ${_this.adaptiveBitrate})';
}


}

/// @nodoc
abstract mixin class $QualitySettingsCopyWith<$Res>  {
  factory $QualitySettingsCopyWith(QualitySettings value, $Res Function(QualitySettings) _then) = _$QualitySettingsCopyWithImpl;
@useResult
$Res call({
 Resolution resolution, FrameRate frameRate, int videoBitrateKbps, bool adaptiveBitrate
});




}
/// @nodoc
class _$QualitySettingsCopyWithImpl<$Res>
    implements $QualitySettingsCopyWith<$Res> {
  _$QualitySettingsCopyWithImpl(this._self, this._then);

  final QualitySettings _self;
  final $Res Function(QualitySettings) _then;

/// Create a copy of QualitySettings
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? resolution = null,Object? frameRate = null,Object? videoBitrateKbps = null,Object? adaptiveBitrate = null,}) {
  return _then(QualitySettings(
resolution: null == resolution ? _self.resolution : resolution // ignore: cast_nullable_to_non_nullable
as Resolution,frameRate: null == frameRate ? _self.frameRate : frameRate // ignore: cast_nullable_to_non_nullable
as FrameRate,videoBitrateKbps: null == videoBitrateKbps ? _self.videoBitrateKbps : videoBitrateKbps // ignore: cast_nullable_to_non_nullable
as int,adaptiveBitrate: null == adaptiveBitrate ? _self.adaptiveBitrate : adaptiveBitrate // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}

}


/// Adds pattern-matching-related methods to [QualitySettings].
extension QualitySettingsPatterns on QualitySettings {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _QualitySettings value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _QualitySettings() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _QualitySettings value)  $default,){
final _that = this;
switch (_that) {
case _QualitySettings():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _QualitySettings value)?  $default,){
final _that = this;
switch (_that) {
case _QualitySettings() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( Resolution resolution,  FrameRate frameRate,  int videoBitrateKbps,  bool adaptiveBitrate)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _QualitySettings() when $default != null:
return $default(_that.resolution,_that.frameRate,_that.videoBitrateKbps,_that.adaptiveBitrate);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( Resolution resolution,  FrameRate frameRate,  int videoBitrateKbps,  bool adaptiveBitrate)  $default,) {final _that = this;
switch (_that) {
case _QualitySettings():
return $default(_that.resolution,_that.frameRate,_that.videoBitrateKbps,_that.adaptiveBitrate);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( Resolution resolution,  FrameRate frameRate,  int videoBitrateKbps,  bool adaptiveBitrate)?  $default,) {final _that = this;
switch (_that) {
case _QualitySettings() when $default != null:
return $default(_that.resolution,_that.frameRate,_that.videoBitrateKbps,_that.adaptiveBitrate);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _QualitySettings implements QualitySettings {
  const _QualitySettings({required this.resolution, required this.frameRate, required this.videoBitrateKbps, required this.adaptiveBitrate});
  factory _QualitySettings.fromJson(Map<String, dynamic> json) => _$QualitySettingsFromJson(json);

@override final  Resolution resolution;
@override final  FrameRate frameRate;
@override final  int videoBitrateKbps;
@override final  bool adaptiveBitrate;

/// Create a copy of QualitySettings
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$QualitySettingsCopyWith<_QualitySettings> get copyWith => __$QualitySettingsCopyWithImpl<_QualitySettings>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$QualitySettingsToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _QualitySettings&&(identical(other.resolution, resolution) || other.resolution == resolution)&&(identical(other.frameRate, frameRate) || other.frameRate == frameRate)&&(identical(other.videoBitrateKbps, videoBitrateKbps) || other.videoBitrateKbps == videoBitrateKbps)&&(identical(other.adaptiveBitrate, adaptiveBitrate) || other.adaptiveBitrate == adaptiveBitrate));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,resolution,frameRate,videoBitrateKbps,adaptiveBitrate);
}

@override
String toString() {
    return 'QualitySettings(resolution: $resolution, frameRate: $frameRate, videoBitrateKbps: $videoBitrateKbps, adaptiveBitrate: $adaptiveBitrate)';
}


}

/// @nodoc
abstract mixin class _$QualitySettingsCopyWith<$Res> implements $QualitySettingsCopyWith<$Res> {
  factory _$QualitySettingsCopyWith(_QualitySettings value, $Res Function(_QualitySettings) _then) = __$QualitySettingsCopyWithImpl;
@override @useResult
$Res call({
 Resolution resolution, FrameRate frameRate, int videoBitrateKbps, bool adaptiveBitrate
});




}
/// @nodoc
class __$QualitySettingsCopyWithImpl<$Res>
    implements _$QualitySettingsCopyWith<$Res> {
  __$QualitySettingsCopyWithImpl(this._self, this._then);

  final _QualitySettings _self;
  final $Res Function(_QualitySettings) _then;

/// Create a copy of QualitySettings
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? resolution = null,Object? frameRate = null,Object? videoBitrateKbps = null,Object? adaptiveBitrate = null,}) {
  return _then(_QualitySettings(
resolution: null == resolution ? _self.resolution : resolution // ignore: cast_nullable_to_non_nullable
as Resolution,frameRate: null == frameRate ? _self.frameRate : frameRate // ignore: cast_nullable_to_non_nullable
as FrameRate,videoBitrateKbps: null == videoBitrateKbps ? _self.videoBitrateKbps : videoBitrateKbps // ignore: cast_nullable_to_non_nullable
as int,adaptiveBitrate: null == adaptiveBitrate ? _self.adaptiveBitrate : adaptiveBitrate // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}


}

// dart format on
