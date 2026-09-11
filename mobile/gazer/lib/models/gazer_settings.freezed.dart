// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'gazer_settings.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$GazerSettings {

 StreamTargetSettings get target; QualitySettings get quality; AudioSourceChoice get audio; bool get forceLibuvc; bool get debugLogs;
/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$GazerSettingsCopyWith<GazerSettings> get copyWith => _$GazerSettingsCopyWithImpl<GazerSettings>(this as GazerSettings, _$identity);

  /// Serializes this GazerSettings to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as GazerSettings;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is GazerSettings&&(identical(other.target, _this.target) || other.target == _this.target)&&(identical(other.quality, _this.quality) || other.quality == _this.quality)&&(identical(other.audio, _this.audio) || other.audio == _this.audio)&&(identical(other.forceLibuvc, _this.forceLibuvc) || other.forceLibuvc == _this.forceLibuvc)&&(identical(other.debugLogs, _this.debugLogs) || other.debugLogs == _this.debugLogs));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as GazerSettings;
  return Object.hash(runtimeType,_this.target,_this.quality,_this.audio,_this.forceLibuvc,_this.debugLogs);
}

@override
String toString() {
  final _this = this as GazerSettings;
  return 'GazerSettings(target: ${_this.target}, quality: ${_this.quality}, audio: ${_this.audio}, forceLibuvc: ${_this.forceLibuvc}, debugLogs: ${_this.debugLogs})';
}


}

/// @nodoc
abstract mixin class $GazerSettingsCopyWith<$Res>  {
  factory $GazerSettingsCopyWith(GazerSettings value, $Res Function(GazerSettings) _then) = _$GazerSettingsCopyWithImpl;
@useResult
$Res call({
 StreamTargetSettings target, QualitySettings quality, AudioSourceChoice audio, bool forceLibuvc, bool debugLogs
});


$StreamTargetSettingsCopyWith<$Res> get target;$QualitySettingsCopyWith<$Res> get quality;

}
/// @nodoc
class _$GazerSettingsCopyWithImpl<$Res>
    implements $GazerSettingsCopyWith<$Res> {
  _$GazerSettingsCopyWithImpl(this._self, this._then);

  final GazerSettings _self;
  final $Res Function(GazerSettings) _then;

/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? target = null,Object? quality = null,Object? audio = null,Object? forceLibuvc = null,Object? debugLogs = null,}) {
  return _then(GazerSettings(
target: null == target ? _self.target : target // ignore: cast_nullable_to_non_nullable
as StreamTargetSettings,quality: null == quality ? _self.quality : quality // ignore: cast_nullable_to_non_nullable
as QualitySettings,audio: null == audio ? _self.audio : audio // ignore: cast_nullable_to_non_nullable
as AudioSourceChoice,forceLibuvc: null == forceLibuvc ? _self.forceLibuvc : forceLibuvc // ignore: cast_nullable_to_non_nullable
as bool,debugLogs: null == debugLogs ? _self.debugLogs : debugLogs // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}
/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$StreamTargetSettingsCopyWith<$Res> get target {
  
  return $StreamTargetSettingsCopyWith<$Res>(_self.target, (value) {
    return _then(_self.copyWith(target: value));
  });
}/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$QualitySettingsCopyWith<$Res> get quality {
  
  return $QualitySettingsCopyWith<$Res>(_self.quality, (value) {
    return _then(_self.copyWith(quality: value));
  });
}
}


/// Adds pattern-matching-related methods to [GazerSettings].
extension GazerSettingsPatterns on GazerSettings {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _GazerSettings value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _GazerSettings() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _GazerSettings value)  $default,){
final _that = this;
switch (_that) {
case _GazerSettings():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _GazerSettings value)?  $default,){
final _that = this;
switch (_that) {
case _GazerSettings() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( StreamTargetSettings target,  QualitySettings quality,  AudioSourceChoice audio,  bool forceLibuvc,  bool debugLogs)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _GazerSettings() when $default != null:
return $default(_that.target,_that.quality,_that.audio,_that.forceLibuvc,_that.debugLogs);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( StreamTargetSettings target,  QualitySettings quality,  AudioSourceChoice audio,  bool forceLibuvc,  bool debugLogs)  $default,) {final _that = this;
switch (_that) {
case _GazerSettings():
return $default(_that.target,_that.quality,_that.audio,_that.forceLibuvc,_that.debugLogs);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( StreamTargetSettings target,  QualitySettings quality,  AudioSourceChoice audio,  bool forceLibuvc,  bool debugLogs)?  $default,) {final _that = this;
switch (_that) {
case _GazerSettings() when $default != null:
return $default(_that.target,_that.quality,_that.audio,_that.forceLibuvc,_that.debugLogs);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _GazerSettings implements GazerSettings {
  const _GazerSettings({required this.target, required this.quality, required this.audio, required this.forceLibuvc, required this.debugLogs});
  factory _GazerSettings.fromJson(Map<String, dynamic> json) => _$GazerSettingsFromJson(json);

@override final  StreamTargetSettings target;
@override final  QualitySettings quality;
@override final  AudioSourceChoice audio;
@override final  bool forceLibuvc;
@override final  bool debugLogs;

/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$GazerSettingsCopyWith<_GazerSettings> get copyWith => __$GazerSettingsCopyWithImpl<_GazerSettings>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$GazerSettingsToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _GazerSettings&&(identical(other.target, target) || other.target == target)&&(identical(other.quality, quality) || other.quality == quality)&&(identical(other.audio, audio) || other.audio == audio)&&(identical(other.forceLibuvc, forceLibuvc) || other.forceLibuvc == forceLibuvc)&&(identical(other.debugLogs, debugLogs) || other.debugLogs == debugLogs));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,target,quality,audio,forceLibuvc,debugLogs);
}

@override
String toString() {
    return 'GazerSettings(target: $target, quality: $quality, audio: $audio, forceLibuvc: $forceLibuvc, debugLogs: $debugLogs)';
}


}

/// @nodoc
abstract mixin class _$GazerSettingsCopyWith<$Res> implements $GazerSettingsCopyWith<$Res> {
  factory _$GazerSettingsCopyWith(_GazerSettings value, $Res Function(_GazerSettings) _then) = __$GazerSettingsCopyWithImpl;
@override @useResult
$Res call({
 StreamTargetSettings target, QualitySettings quality, AudioSourceChoice audio, bool forceLibuvc, bool debugLogs
});


@override $StreamTargetSettingsCopyWith<$Res> get target;@override $QualitySettingsCopyWith<$Res> get quality;

}
/// @nodoc
class __$GazerSettingsCopyWithImpl<$Res>
    implements _$GazerSettingsCopyWith<$Res> {
  __$GazerSettingsCopyWithImpl(this._self, this._then);

  final _GazerSettings _self;
  final $Res Function(_GazerSettings) _then;

/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? target = null,Object? quality = null,Object? audio = null,Object? forceLibuvc = null,Object? debugLogs = null,}) {
  return _then(_GazerSettings(
target: null == target ? _self.target : target // ignore: cast_nullable_to_non_nullable
as StreamTargetSettings,quality: null == quality ? _self.quality : quality // ignore: cast_nullable_to_non_nullable
as QualitySettings,audio: null == audio ? _self.audio : audio // ignore: cast_nullable_to_non_nullable
as AudioSourceChoice,forceLibuvc: null == forceLibuvc ? _self.forceLibuvc : forceLibuvc // ignore: cast_nullable_to_non_nullable
as bool,debugLogs: null == debugLogs ? _self.debugLogs : debugLogs // ignore: cast_nullable_to_non_nullable
as bool,
  ));
}

/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$StreamTargetSettingsCopyWith<$Res> get target {
  
  return $StreamTargetSettingsCopyWith<$Res>(_self.target, (value) {
    return _then(_self.copyWith(target: value));
  });
}/// Create a copy of GazerSettings
/// with the given fields replaced by the non-null parameter values.
@override
@pragma('vm:prefer-inline')
$QualitySettingsCopyWith<$Res> get quality {
  
  return $QualitySettingsCopyWith<$Res>(_self.quality, (value) {
    return _then(_self.copyWith(quality: value));
  });
}
}

// dart format on
