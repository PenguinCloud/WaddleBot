// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'stream_target_settings.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$StreamTargetSettings {

 String get url; String? get streamKey; String? get username; String? get password;
/// Create a copy of StreamTargetSettings
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$StreamTargetSettingsCopyWith<StreamTargetSettings> get copyWith => _$StreamTargetSettingsCopyWithImpl<StreamTargetSettings>(this as StreamTargetSettings, _$identity);

  /// Serializes this StreamTargetSettings to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as StreamTargetSettings;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is StreamTargetSettings&&(identical(other.url, _this.url) || other.url == _this.url)&&(identical(other.streamKey, _this.streamKey) || other.streamKey == _this.streamKey)&&(identical(other.username, _this.username) || other.username == _this.username)&&(identical(other.password, _this.password) || other.password == _this.password));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as StreamTargetSettings;
  return Object.hash(runtimeType,_this.url,_this.streamKey,_this.username,_this.password);
}



}

/// @nodoc
abstract mixin class $StreamTargetSettingsCopyWith<$Res>  {
  factory $StreamTargetSettingsCopyWith(StreamTargetSettings value, $Res Function(StreamTargetSettings) _then) = _$StreamTargetSettingsCopyWithImpl;
@useResult
$Res call({
 String url, String? streamKey, String? username, String? password
});




}
/// @nodoc
class _$StreamTargetSettingsCopyWithImpl<$Res>
    implements $StreamTargetSettingsCopyWith<$Res> {
  _$StreamTargetSettingsCopyWithImpl(this._self, this._then);

  final StreamTargetSettings _self;
  final $Res Function(StreamTargetSettings) _then;

/// Create a copy of StreamTargetSettings
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? url = null,Object? streamKey = freezed,Object? username = freezed,Object? password = freezed,}) {
  return _then(StreamTargetSettings(
url: null == url ? _self.url : url // ignore: cast_nullable_to_non_nullable
as String,streamKey: freezed == streamKey ? _self.streamKey : streamKey // ignore: cast_nullable_to_non_nullable
as String?,username: freezed == username ? _self.username : username // ignore: cast_nullable_to_non_nullable
as String?,password: freezed == password ? _self.password : password // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}

}


/// Adds pattern-matching-related methods to [StreamTargetSettings].
extension StreamTargetSettingsPatterns on StreamTargetSettings {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _StreamTargetSettings value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _StreamTargetSettings() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _StreamTargetSettings value)  $default,){
final _that = this;
switch (_that) {
case _StreamTargetSettings():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _StreamTargetSettings value)?  $default,){
final _that = this;
switch (_that) {
case _StreamTargetSettings() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( String url,  String? streamKey,  String? username,  String? password)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _StreamTargetSettings() when $default != null:
return $default(_that.url,_that.streamKey,_that.username,_that.password);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( String url,  String? streamKey,  String? username,  String? password)  $default,) {final _that = this;
switch (_that) {
case _StreamTargetSettings():
return $default(_that.url,_that.streamKey,_that.username,_that.password);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( String url,  String? streamKey,  String? username,  String? password)?  $default,) {final _that = this;
switch (_that) {
case _StreamTargetSettings() when $default != null:
return $default(_that.url,_that.streamKey,_that.username,_that.password);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _StreamTargetSettings extends StreamTargetSettings {
  const _StreamTargetSettings({required this.url, this.streamKey, this.username, this.password}): super._();
  factory _StreamTargetSettings.fromJson(Map<String, dynamic> json) => _$StreamTargetSettingsFromJson(json);

@override final  String url;
@override final  String? streamKey;
@override final  String? username;
@override final  String? password;

/// Create a copy of StreamTargetSettings
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$StreamTargetSettingsCopyWith<_StreamTargetSettings> get copyWith => __$StreamTargetSettingsCopyWithImpl<_StreamTargetSettings>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$StreamTargetSettingsToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _StreamTargetSettings&&(identical(other.url, url) || other.url == url)&&(identical(other.streamKey, streamKey) || other.streamKey == streamKey)&&(identical(other.username, username) || other.username == username)&&(identical(other.password, password) || other.password == password));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,url,streamKey,username,password);
}



}

/// @nodoc
abstract mixin class _$StreamTargetSettingsCopyWith<$Res> implements $StreamTargetSettingsCopyWith<$Res> {
  factory _$StreamTargetSettingsCopyWith(_StreamTargetSettings value, $Res Function(_StreamTargetSettings) _then) = __$StreamTargetSettingsCopyWithImpl;
@override @useResult
$Res call({
 String url, String? streamKey, String? username, String? password
});




}
/// @nodoc
class __$StreamTargetSettingsCopyWithImpl<$Res>
    implements _$StreamTargetSettingsCopyWith<$Res> {
  __$StreamTargetSettingsCopyWithImpl(this._self, this._then);

  final _StreamTargetSettings _self;
  final $Res Function(_StreamTargetSettings) _then;

/// Create a copy of StreamTargetSettings
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? url = null,Object? streamKey = freezed,Object? username = freezed,Object? password = freezed,}) {
  return _then(_StreamTargetSettings(
url: null == url ? _self.url : url // ignore: cast_nullable_to_non_nullable
as String,streamKey: freezed == streamKey ? _self.streamKey : streamKey // ignore: cast_nullable_to_non_nullable
as String?,username: freezed == username ? _self.username : username // ignore: cast_nullable_to_non_nullable
as String?,password: freezed == password ? _self.password : password // ignore: cast_nullable_to_non_nullable
as String?,
  ));
}


}

// dart format on
