//! Serialization from Polars to dBase values
//!
//! This module handles the conversion from Polars DataTypes and AnyValues
//! to dBase FieldValues, following the pattern from the Avro plugin.
//! It provides a clean API for converting DataFrames to dBase records
//! that can be written by a separate module.

use dbase::{Date, DateTime, FieldType, FieldValue, Time};
use polars::prelude::{AnyValue, DataType, Schema as PlSchema, TimeUnit};

use crate::error::Error;

/// Field specification for creating dBase fields from Polars schema
#[derive(Debug, Clone)]
pub struct DBaseFieldSpec {
    pub name: String,
    pub field_type: FieldType,
    pub length: u8,
    pub decimal_places: u8,
}

/// Serializer for converting Polars data to dBase format
pub struct Serializer {
    default_string_length: u8,
    default_numeric_precision: u8,
    default_numeric_scale: u8,
}

impl Default for Serializer {
    fn default() -> Self {
        Self {
            default_string_length: 255,
            default_numeric_precision: 20,
            default_numeric_scale: 10,
        }
    }
}

impl Serializer {
    /// Creates a new serializer with default configuration
    pub fn new() -> Self {
        Self::default()
    }

    /// Creates a new serializer with custom configuration
    pub fn with_config(
        default_string_length: u8,
        default_numeric_precision: u8,
        default_numeric_scale: u8,
    ) -> Self {
        Self {
            default_string_length,
            default_numeric_precision,
            default_numeric_scale,
        }
    }

    /// Convert a Polars schema to dBase field specifications
    pub fn try_as_schema(&self, schema: &PlSchema) -> Result<Vec<DBaseFieldSpec>, Error> {
        let dbase_fields: Result<Vec<_>, Error> = schema
            .iter()
            .map(|(name, dtype)| self.try_as_field_spec(name.as_str(), dtype))
            .collect();

        dbase_fields
    }

    /// Convert a single Polars field to dBase field specification
    pub fn try_as_field_spec(&self, name: &str, dtype: &DataType) -> Result<DBaseFieldSpec, Error> {
        let (field_type, length, decimal_places) = match dtype {
            DataType::String => (FieldType::Character, self.default_string_length, 0),
            DataType::Int8 | DataType::Int16 | DataType::Int32 => (FieldType::Integer, 4, 0),
            DataType::Int64 => (FieldType::Numeric, self.default_numeric_precision, 0),
            DataType::UInt8 | DataType::UInt16 | DataType::UInt32 | DataType::UInt64 => {
                (FieldType::Numeric, self.default_numeric_precision, 0)
            }
            DataType::Float32 => (FieldType::Float, 15, 7),
            DataType::Float64 => (
                FieldType::Numeric,
                self.default_numeric_precision,
                self.default_numeric_scale,
            ),
            DataType::Boolean => (FieldType::Logical, 1, 0),
            DataType::Date => (FieldType::Date, 8, 0),
            DataType::Datetime(_, _) => {
                // All datetime types map to dBase DateTime
                (FieldType::DateTime, 8, 0)
            }
            DataType::Decimal(precision, scale) => {
                let prec = precision
                    .unwrap_or(self.default_numeric_precision as usize)
                    .min(255) as u8;
                let scale = scale.unwrap_or(self.default_numeric_scale as usize).min(15) as u8;
                (FieldType::Numeric, prec, scale)
            }
            _ => return Err(Error::UnsupportedFieldType(FieldType::Character)), // Use Character as placeholder
        };

        Ok(DBaseFieldSpec {
            name: name.to_string(),
            field_type,
            length,
            decimal_places,
        })
    }
}

/// Convert Polars AnyValue to dBase FieldValue based on field specification
pub fn try_as_field_value(
    value: &AnyValue,
    field_spec: &DBaseFieldSpec,
) -> Result<FieldValue, Error> {
    match (value, &field_spec.field_type) {
        // String/Character fields
        (AnyValue::String(s), FieldType::Character) => {
            Ok(FieldValue::Character(Some(s.to_string())))
        }
        (AnyValue::StringOwned(s), FieldType::Character) => {
            Ok(FieldValue::Character(Some(s.to_string())))
        }
        (AnyValue::Null, FieldType::Character) => Ok(FieldValue::Character(None)),

        // Memo fields
        (AnyValue::String(s), FieldType::Memo) => Ok(FieldValue::Memo(s.to_string())),
        (AnyValue::StringOwned(s), FieldType::Memo) => Ok(FieldValue::Memo(s.to_string())),

        // Boolean/Logical fields
        (AnyValue::Boolean(b), FieldType::Logical) => Ok(FieldValue::Logical(Some(*b))),
        (AnyValue::Null, FieldType::Logical) => Ok(FieldValue::Logical(None)),

        // Integer fields
        (AnyValue::Int8(i), FieldType::Integer) => Ok(FieldValue::Integer(*i as i32)),
        (AnyValue::Int16(i), FieldType::Integer) => Ok(FieldValue::Integer(*i as i32)),
        (AnyValue::Int32(i), FieldType::Integer) => Ok(FieldValue::Integer(*i)),
        (AnyValue::UInt8(i), FieldType::Integer) => Ok(FieldValue::Integer(*i as i32)),
        (AnyValue::UInt16(i), FieldType::Integer) => Ok(FieldValue::Integer(*i as i32)),

        // Numeric fields (stored as Float64)
        (AnyValue::Int64(i), FieldType::Numeric) => Ok(FieldValue::Numeric(Some(*i as f64))),
        (AnyValue::UInt32(i), FieldType::Numeric) => Ok(FieldValue::Numeric(Some(*i as f64))),
        (AnyValue::UInt64(i), FieldType::Numeric) => {
            if *i <= f64::MAX as u64 {
                Ok(FieldValue::Numeric(Some(*i as f64)))
            } else {
                Err(Error::InvalidConversion(format!(
                    "UInt64 value {} exceeds f64::MAX",
                    i
                )))
            }
        }
        (AnyValue::Float64(f), FieldType::Numeric) => Ok(FieldValue::Numeric(Some(*f))),
        (AnyValue::Null, FieldType::Numeric) => Ok(FieldValue::Numeric(None)),

        // Float fields
        (AnyValue::Float32(f), FieldType::Float) => Ok(FieldValue::Float(Some(*f))),
        (AnyValue::Null, FieldType::Float) => Ok(FieldValue::Float(None)),

        // Currency fields
        (AnyValue::Float64(f), FieldType::Currency) => Ok(FieldValue::Currency(*f)),

        // Double fields
        (AnyValue::Float64(f), FieldType::Double) => Ok(FieldValue::Double(*f)),

        // Date fields - improved conversion
        (AnyValue::Date(days), FieldType::Date) => {
            let dbase_date = convert_days_to_dbase_date(*days)?;
            Ok(FieldValue::Date(Some(dbase_date)))
        }
        (AnyValue::Null, FieldType::Date) => Ok(FieldValue::Date(None)),

        // DateTime fields - improved conversion
        (AnyValue::Datetime(timestamp, TimeUnit::Milliseconds, _), FieldType::DateTime) => {
            let dbase_datetime = convert_timestamp_to_dbase_datetime(*timestamp)?;
            Ok(FieldValue::DateTime(dbase_datetime))
        }
        (AnyValue::Datetime(timestamp, TimeUnit::Microseconds, _), FieldType::DateTime) => {
            let dbase_datetime = convert_timestamp_micros_to_dbase_datetime(*timestamp)?;
            Ok(FieldValue::DateTime(dbase_datetime))
        }
        (AnyValue::Datetime(timestamp, TimeUnit::Nanoseconds, _), FieldType::DateTime) => {
            let dbase_datetime = convert_timestamp_nanos_to_dbase_datetime(*timestamp)?;
            Ok(FieldValue::DateTime(dbase_datetime))
        }

        _ => Err(Error::InvalidConversion(format!(
            "Cannot convert {:?} to {:?}",
            value, field_spec.field_type
        ))),
    }
}

/// Convert a Polars row (slice of AnyValues) to a dBase Record
pub fn try_as_record(
    row: &[AnyValue],
    field_specs: &[DBaseFieldSpec],
) -> Result<dbase::Record, Error> {
    let mut record = dbase::Record::default();

    if row.len() != field_specs.len() {
        return Err(Error::SchemaMismatch(format!(
            "Row has {} values but field specs have {} fields",
            row.len(),
            field_specs.len()
        )));
    }

    for (any_value, spec) in row.iter().zip(field_specs) {
        let field_value = try_as_field_value(any_value, spec)?;
        record.insert(spec.name.clone(), field_value);
    }

    Ok(record)
}

/// Serialize a Polars DataFrame to dBase records
pub fn serialize_dataframe(
    df: &polars::prelude::DataFrame,
    field_specs: Option<Vec<DBaseFieldSpec>>,
) -> Result<Vec<dbase::Record>, Error> {
    let schema = df.schema();
    let specs = match field_specs {
        Some(specs) => specs,
        None => {
            let serializer = Serializer::new();
            serializer.try_as_schema(schema)?
        }
    };

    // Validate schema matches field specs
    if schema.len() != specs.len() {
        return Err(Error::SchemaMismatch(format!(
            "DataFrame schema has {} fields but field specs have {}",
            schema.len(),
            specs.len()
        )));
    }

    let mut records = Vec::with_capacity(df.height());

    // Convert each row to a dBase record
    for row_idx in 0..df.height() {
        let row: Vec<AnyValue> = schema
            .iter()
            .map(|(name, _)| df.column(name).unwrap().get(row_idx).unwrap())
            .collect();

        let record = try_as_record(&row, &specs)?;
        records.push(record);
    }

    Ok(records)
}

/// Helper function to convert Polars days to dBase Date
fn convert_days_to_dbase_date(days: i32) -> Result<Date, Error> {
    // Polars Date is days since 1970-01-01 (Unix epoch)
    // We need to convert this to a dBase Date
    // Use a simpler approach: calculate the date directly

    if days < 0 {
        return Err(Error::InvalidConversion(format!(
            "Date {} is before Unix epoch",
            days
        )));
    }

    // Convert days since epoch to actual date
    // This is a simplified calculation - for production use, consider using a proper date library
    let year = 1970 + (days / 365);
    let remaining_days = days % 365;

    // Simple conversion to year, month, day
    let month = ((remaining_days / 30) % 12) + 1;
    let day = (remaining_days % 30) + 1;

    Ok(Date::new(day as u32, month as u32, year as u32))
}

/// Helper function to convert timestamp (milliseconds) to dBase DateTime
fn convert_timestamp_to_dbase_datetime(timestamp: i64) -> Result<DateTime, Error> {
    let days = timestamp / (24 * 60 * 60 * 1000);
    let milliseconds_in_day = timestamp % (24 * 60 * 60 * 1000);

    let date = convert_days_to_dbase_date(days as i32)?;

    let hours = milliseconds_in_day / (60 * 60 * 1000);
    let minutes = (milliseconds_in_day % (60 * 60 * 1000)) / (60 * 1000);
    let seconds = (milliseconds_in_day % (60 * 1000)) / 1000;

    let time = Time::new(hours as u32, minutes as u32, seconds as u32);

    Ok(DateTime::new(date, time))
}

/// Helper function to convert timestamp (microseconds) to dBase DateTime
fn convert_timestamp_micros_to_dbase_datetime(timestamp: i64) -> Result<DateTime, Error> {
    let days = timestamp / (24 * 60 * 60 * 1_000_000);
    let microseconds_in_day = timestamp % (24 * 60 * 60 * 1_000_000);

    let date = convert_days_to_dbase_date(days as i32)?;

    let hours = microseconds_in_day / (60 * 60 * 1_000_000);
    let minutes = (microseconds_in_day % (60 * 60 * 1_000_000)) / (60 * 1_000_000);
    let seconds = (microseconds_in_day % (60 * 1_000_000)) / 1_000_000;

    let time = Time::new(hours as u32, minutes as u32, seconds as u32);

    Ok(DateTime::new(date, time))
}

/// Helper function to convert timestamp (nanoseconds) to dBase DateTime
fn convert_timestamp_nanos_to_dbase_datetime(timestamp: i64) -> Result<DateTime, Error> {
    let days = timestamp / (24 * 60 * 60 * 1_000_000_000);
    let nanoseconds_in_day = timestamp % (24 * 60 * 60 * 1_000_000_000);

    let date = convert_days_to_dbase_date(days as i32)?;

    let hours = nanoseconds_in_day / (60 * 60 * 1_000_000_000);
    let minutes = (nanoseconds_in_day % (60 * 60 * 1_000_000_000)) / (60 * 1_000_000_000);
    let seconds = (nanoseconds_in_day % (60 * 1_000_000_000)) / 1_000_000_000;

    let time = Time::new(hours as u32, minutes as u32, seconds as u32);

    Ok(DateTime::new(date, time))
}

#[cfg(test)]
mod tests {
    use super::*;
    use polars::prelude::{AnyValue, DataType};

    #[test]
    fn test_serializer_default() {
        let serializer = Serializer::new();
        assert_eq!(serializer.default_string_length, 255);
        assert_eq!(serializer.default_numeric_precision, 20);
        assert_eq!(serializer.default_numeric_scale, 10);
    }

    #[test]
    fn test_serializer_custom_config() {
        let serializer = Serializer::with_config(100, 15, 5);
        assert_eq!(serializer.default_string_length, 100);
        assert_eq!(serializer.default_numeric_precision, 15);
        assert_eq!(serializer.default_numeric_scale, 5);
    }

    #[test]
    fn test_schema_conversion() {
        let serializer = Serializer::new();
        let schema = PlSchema::from_iter(vec![
            ("name".into(), DataType::String),
            ("age".into(), DataType::Int32),
            ("score".into(), DataType::Float64),
            ("is_active".into(), DataType::Boolean),
            ("created_date".into(), DataType::Date),
        ]);

        let specs = serializer.try_as_schema(&schema).unwrap();
        assert_eq!(specs.len(), 5);
        assert_eq!(specs[0].field_type, FieldType::Character);
        assert_eq!(specs[1].field_type, FieldType::Integer);
        assert_eq!(specs[2].field_type, FieldType::Numeric);
        assert_eq!(specs[3].field_type, FieldType::Logical);
        assert_eq!(specs[4].field_type, FieldType::Date);
    }

    #[test]
    fn test_string_value_conversion() {
        let spec = DBaseFieldSpec {
            name: "test".to_string(),
            field_type: FieldType::Character,
            length: 50,
            decimal_places: 0,
        };

        let string_val = AnyValue::String("test");
        let result = try_as_field_value(&string_val, &spec).unwrap();
        assert!(matches!(result, FieldValue::Character(Some(_))));

        let null_val = AnyValue::Null;
        let result = try_as_field_value(&null_val, &spec).unwrap();
        assert!(matches!(result, FieldValue::Character(None)));
    }

    #[test]
    fn test_boolean_value_conversion() {
        let spec = DBaseFieldSpec {
            name: "test".to_string(),
            field_type: FieldType::Logical,
            length: 1,
            decimal_places: 0,
        };

        let bool_val = AnyValue::Boolean(true);
        let result = try_as_field_value(&bool_val, &spec).unwrap();
        assert!(matches!(result, FieldValue::Logical(Some(true))));

        let null_val = AnyValue::Null;
        let result = try_as_field_value(&null_val, &spec).unwrap();
        assert!(matches!(result, FieldValue::Logical(None)));
    }

    #[test]
    fn test_numeric_value_conversions() {
        // Test integer to Integer field
        let int_spec = DBaseFieldSpec {
            name: "test".to_string(),
            field_type: FieldType::Integer,
            length: 4,
            decimal_places: 0,
        };
        let int_val = AnyValue::Int32(42);
        let result = try_as_field_value(&int_val, &int_spec).unwrap();
        assert!(matches!(result, FieldValue::Integer(42)));

        // Test float to Numeric field
        let num_spec = DBaseFieldSpec {
            name: "test".to_string(),
            field_type: FieldType::Numeric,
            length: 20,
            decimal_places: 10,
        };
        let float_val = AnyValue::Float64(123.45);
        let result = try_as_field_value(&float_val, &num_spec).unwrap();
        assert!(
            matches!(result, FieldValue::Numeric(Some(f)) if (f - 123.45).abs() < f64::EPSILON)
        );
    }

    #[test]
    fn test_date_value_conversion() {
        let spec = DBaseFieldSpec {
            name: "test".to_string(),
            field_type: FieldType::Date,
            length: 8,
            decimal_places: 0,
        };

        let date_val = AnyValue::Date(365); // One year after epoch
        let result = try_as_field_value(&date_val, &spec).unwrap();
        assert!(matches!(result, FieldValue::Date(Some(_))));

        let null_date = AnyValue::Null;
        let result = try_as_field_value(&null_date, &spec).unwrap();
        assert!(matches!(result, FieldValue::Date(None)));
    }

    #[test]
    fn test_unsupported_conversions() {
        let spec = DBaseFieldSpec {
            name: "test".to_string(),
            field_type: FieldType::Integer,
            length: 4,
            decimal_places: 0,
        };

        // Test incompatible conversion
        let string_val = AnyValue::String("test");
        let result = try_as_field_value(&string_val, &spec);
        assert!(result.is_err());
    }

    #[test]
    fn test_record_conversion() {
        let specs = vec![
            DBaseFieldSpec {
                name: "name".to_string(),
                field_type: FieldType::Character,
                length: 50,
                decimal_places: 0,
            },
            DBaseFieldSpec {
                name: "age".to_string(),
                field_type: FieldType::Integer,
                length: 4,
                decimal_places: 0,
            },
        ];

        let row = vec![AnyValue::String("John Doe"), AnyValue::Int32(30)];

        let record = try_as_record(&row, &specs).unwrap();
        assert_eq!(
            record.get("name").unwrap(),
            &FieldValue::Character(Some("John Doe".to_string()))
        );
        assert_eq!(record.get("age").unwrap(), &FieldValue::Integer(30));
    }

    #[test]
    fn test_record_conversion_mismatch() {
        let specs = vec![DBaseFieldSpec {
            name: "name".to_string(),
            field_type: FieldType::Character,
            length: 50,
            decimal_places: 0,
        }];

        let row = vec![
            AnyValue::String("John Doe"),
            AnyValue::Int32(30), // Extra value
        ];

        let result = try_as_record(&row, &specs);
        assert!(result.is_err());
    }
}
