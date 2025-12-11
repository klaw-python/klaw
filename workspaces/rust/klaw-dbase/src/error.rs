//! Error types for the optimal DBF implementation

use std::fmt;

/// Custom error type for dBase deserialization and scanning
#[derive(Debug)]
pub enum Error {
    /// Unsupported dBase field type
    UnsupportedFieldType(dbase::FieldType),

    /// Invalid field value conversion
    InvalidConversion(String),

    /// Internal error with message
    InternalError { message: String },

    /// Schema mismatch
    SchemaMismatch(String),

    /// DBC-specific errors
    DbcError(String),

    /// Compression-specific errors
    CompressionError(String),

    /// Huffman bridge errors
    HuffmanBridgeError(String),

    /// LZSS encoding errors
    LzssError(String),

    /// Constriction errors
    ConstrictionError(String),

    /// Encoding error
    EncodingError(String),

    /// Non-matching schemas between chunks
    NonMatchingSchemas,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::UnsupportedFieldType(field_type) => {
                write!(f, "Unsupported dBase field type: {:?}", field_type)
            }
            Error::InvalidConversion(msg) => {
                write!(f, "Invalid field value conversion: {}", msg)
            }
            Error::InternalError { message } => {
                write!(f, "Internal error: {}", message)
            }
            Error::SchemaMismatch(msg) => {
                write!(f, "Schema mismatch: {}", msg)
            }
            Error::DbcError(msg) => {
                write!(f, "DBC error: {}", msg)
            }
            Error::CompressionError(msg) => {
                write!(f, "Compression error: {}", msg)
            }
            Error::HuffmanBridgeError(msg) => {
                write!(f, "Huffman bridge error: {}", msg)
            }
            Error::LzssError(msg) => {
                write!(f, "LZSS error: {}", msg)
            }
            Error::ConstrictionError(msg) => {
                write!(f, "Constriction error: {}", msg)
            }
            Error::EncodingError(msg) => {
                write!(f, "Encoding error: {}", msg)
            }
            Error::NonMatchingSchemas => {
                write!(f, "Non-matching schemas between chunks")
            }
        }
    }
}

impl std::error::Error for Error {}

// Error conversions
impl From<std::io::Error> for Error {
    fn from(err: std::io::Error) -> Self {
        Error::InternalError {
            message: format!("I/O error: {}", err),
        }
    }
}

impl From<dbase::Error> for Error {
    fn from(err: dbase::Error) -> Self {
        Error::InternalError {
            message: format!("DBase error: {}", err),
        }
    }
}

impl From<dbase::FieldIOError> for Error {
    fn from(err: dbase::FieldIOError) -> Self {
        Error::InternalError {
            message: format!("Field I/O error: {}", err),
        }
    }
}

impl From<polars::error::PolarsError> for Error {
    fn from(err: polars::error::PolarsError) -> Self {
        Error::InternalError {
            message: format!("Polars error: {}", err),
        }
    }
}

impl From<explode::Error> for Error {
    fn from(err: explode::Error) -> Self {
        Error::DbcError(format!("Explode decompression error: {}", err))
    }
}

// Compression error conversions
impl<BE> From<constriction::CoderError<constriction::DefaultEncoderFrontendError, BE>> for Error
where
    BE: std::fmt::Display,
{
    fn from(err: constriction::CoderError<constriction::DefaultEncoderFrontendError, BE>) -> Self {
        Error::ConstrictionError(format!("Constriction coder error: {}", err))
    }
}

impl From<constriction::NanError> for Error {
    fn from(err: constriction::NanError) -> Self {
        Error::ConstrictionError(format!("Constriction NaN error: {}", err))
    }
}
