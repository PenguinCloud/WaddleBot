// GENERATED CODE - DO NOT MODIFY BY HAND
// coverage:ignore-file
// ignore_for_file: type=lint, type=warning, deprecated_member_use, deprecated_member_use_from_same_package
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'license_state.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

// GENERATED CODE - DO NOT MODIFY BY HAND
// dart format off
T _$identity<T>(T value) => value;

/// @nodoc
mixin _$LicenseState {

 LicenseStatus get status; Map<String, bool> get flags; DateTime? get lastFetched; String get deviceId;
/// Create a copy of LicenseState
/// with the given fields replaced by the non-null parameter values.
@JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
$LicenseStateCopyWith<LicenseState> get copyWith => _$LicenseStateCopyWithImpl<LicenseState>(this as LicenseState, _$identity);

  /// Serializes this LicenseState to a JSON map.
  Map<String, dynamic> toJson();


@override
bool operator ==(Object other) {
  final _this = this as LicenseState;
  return identical(this, other) || (other.runtimeType == runtimeType&&other is LicenseState&&(identical(other.status, _this.status) || other.status == _this.status)&&const DeepCollectionEquality().equals(other.flags, _this.flags)&&(identical(other.lastFetched, _this.lastFetched) || other.lastFetched == _this.lastFetched)&&(identical(other.deviceId, _this.deviceId) || other.deviceId == _this.deviceId));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
  final _this = this as LicenseState;
  return Object.hash(runtimeType,_this.status,const DeepCollectionEquality().hash(_this.flags),_this.lastFetched,_this.deviceId);
}

@override
String toString() {
  final _this = this as LicenseState;
  return 'LicenseState(status: ${_this.status}, flags: ${_this.flags}, lastFetched: ${_this.lastFetched}, deviceId: ${_this.deviceId})';
}


}

/// @nodoc
abstract mixin class $LicenseStateCopyWith<$Res>  {
  factory $LicenseStateCopyWith(LicenseState value, $Res Function(LicenseState) _then) = _$LicenseStateCopyWithImpl;
@useResult
$Res call({
 LicenseStatus status, Map<String, bool> flags, DateTime? lastFetched, String deviceId
});




}
/// @nodoc
class _$LicenseStateCopyWithImpl<$Res>
    implements $LicenseStateCopyWith<$Res> {
  _$LicenseStateCopyWithImpl(this._self, this._then);

  final LicenseState _self;
  final $Res Function(LicenseState) _then;

/// Create a copy of LicenseState
/// with the given fields replaced by the non-null parameter values.
@pragma('vm:prefer-inline') @override $Res call({Object? status = null,Object? flags = null,Object? lastFetched = freezed,Object? deviceId = null,}) {
  return _then(LicenseState(
status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as LicenseStatus,flags: null == flags ? _self.flags : flags // ignore: cast_nullable_to_non_nullable
as Map<String, bool>,lastFetched: freezed == lastFetched ? _self.lastFetched : lastFetched // ignore: cast_nullable_to_non_nullable
as DateTime?,deviceId: null == deviceId ? _self.deviceId : deviceId // ignore: cast_nullable_to_non_nullable
as String,
  ));
}

}


/// Adds pattern-matching-related methods to [LicenseState].
extension LicenseStatePatterns on LicenseState {
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

@optionalTypeArgs TResult maybeMap<TResult extends Object?>(TResult Function( _LicenseState value)?  $default,{required TResult orElse(),}){
final _that = this;
switch (_that) {
case _LicenseState() when $default != null:
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

@optionalTypeArgs TResult map<TResult extends Object?>(TResult Function( _LicenseState value)  $default,){
final _that = this;
switch (_that) {
case _LicenseState():
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

@optionalTypeArgs TResult? mapOrNull<TResult extends Object?>(TResult? Function( _LicenseState value)?  $default,){
final _that = this;
switch (_that) {
case _LicenseState() when $default != null:
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

@optionalTypeArgs TResult maybeWhen<TResult extends Object?>(TResult Function( LicenseStatus status,  Map<String, bool> flags,  DateTime? lastFetched,  String deviceId)?  $default,{required TResult orElse(),}) {final _that = this;
switch (_that) {
case _LicenseState() when $default != null:
return $default(_that.status,_that.flags,_that.lastFetched,_that.deviceId);case _:
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

@optionalTypeArgs TResult when<TResult extends Object?>(TResult Function( LicenseStatus status,  Map<String, bool> flags,  DateTime? lastFetched,  String deviceId)  $default,) {final _that = this;
switch (_that) {
case _LicenseState():
return $default(_that.status,_that.flags,_that.lastFetched,_that.deviceId);case _:
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

@optionalTypeArgs TResult? whenOrNull<TResult extends Object?>(TResult? Function( LicenseStatus status,  Map<String, bool> flags,  DateTime? lastFetched,  String deviceId)?  $default,) {final _that = this;
switch (_that) {
case _LicenseState() when $default != null:
return $default(_that.status,_that.flags,_that.lastFetched,_that.deviceId);case _:
  return null;

}
}

}

/// @nodoc
@JsonSerializable()

class _LicenseState implements LicenseState {
  const _LicenseState({required this.status, required  Map<String, bool> flags, this.lastFetched, required this.deviceId}): _flags = flags;
  factory _LicenseState.fromJson(Map<String, dynamic> json) => _$LicenseStateFromJson(json);

@override final  LicenseStatus status;
 final  Map<String, bool> _flags;
@override Map<String, bool> get flags {
  if (_flags is EqualUnmodifiableMapView) return _flags;
  // ignore: implicit_dynamic_type
  return EqualUnmodifiableMapView(_flags);
}

@override final  DateTime? lastFetched;
@override final  String deviceId;

/// Create a copy of LicenseState
/// with the given fields replaced by the non-null parameter values.
@override @JsonKey(includeFromJson: false, includeToJson: false)
@pragma('vm:prefer-inline')
_$LicenseStateCopyWith<_LicenseState> get copyWith => __$LicenseStateCopyWithImpl<_LicenseState>(this, _$identity);

@override
Map<String, dynamic> toJson() {
  return _$LicenseStateToJson(this, );
}

@override
bool operator ==(Object other) {
    return identical(this, other) || (other.runtimeType == runtimeType&&other is _LicenseState&&(identical(other.status, status) || other.status == status)&&const DeepCollectionEquality().equals(other.flags, _flags)&&(identical(other.lastFetched, lastFetched) || other.lastFetched == lastFetched)&&(identical(other.deviceId, deviceId) || other.deviceId == deviceId));
}

@JsonKey(includeFromJson: false, includeToJson: false)
@override
int get hashCode {
    return Object.hash(runtimeType,status,const DeepCollectionEquality().hash(_flags),lastFetched,deviceId);
}

@override
String toString() {
    return 'LicenseState(status: $status, flags: $flags, lastFetched: $lastFetched, deviceId: $deviceId)';
}


}

/// @nodoc
abstract mixin class _$LicenseStateCopyWith<$Res> implements $LicenseStateCopyWith<$Res> {
  factory _$LicenseStateCopyWith(_LicenseState value, $Res Function(_LicenseState) _then) = __$LicenseStateCopyWithImpl;
@override @useResult
$Res call({
 LicenseStatus status, Map<String, bool> flags, DateTime? lastFetched, String deviceId
});




}
/// @nodoc
class __$LicenseStateCopyWithImpl<$Res>
    implements _$LicenseStateCopyWith<$Res> {
  __$LicenseStateCopyWithImpl(this._self, this._then);

  final _LicenseState _self;
  final $Res Function(_LicenseState) _then;

/// Create a copy of LicenseState
/// with the given fields replaced by the non-null parameter values.
@override @pragma('vm:prefer-inline') $Res call({Object? status = null,Object? flags = null,Object? lastFetched = freezed,Object? deviceId = null,}) {
  return _then(_LicenseState(
status: null == status ? _self.status : status // ignore: cast_nullable_to_non_nullable
as LicenseStatus,flags: null == flags ? _self._flags : flags // ignore: cast_nullable_to_non_nullable
as Map<String, bool>,lastFetched: freezed == lastFetched ? _self.lastFetched : lastFetched // ignore: cast_nullable_to_non_nullable
as DateTime?,deviceId: null == deviceId ? _self.deviceId : deviceId // ignore: cast_nullable_to_non_nullable
as String,
  ));
}


}

// dart format on
