#!/bin/bash
# Solution – only runs with "Check course package" in the editor, never for participants
cd ~/Agent-Files/pdf && pdfunite invoice-march.pdf invoice-april.pdf invoices-total.pdf
